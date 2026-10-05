"""Agent 门面：把组件装配成引擎，跑回合并把事件桥接到 Bus。

治理接线（docs/plans/2026-10-02-m3-tasks.md §2）：run 前对**既有历史**
调用治理器 enforce（新输入本就该全量保留，压缩目标只能是旧内容）并
回写引擎；逐事件 emit 到 Bus——记忆写路径（TurnCommitted 订阅）由此
接通。门面代行装配器的 setup 步骤（记忆实现的事件订阅在此登记）。
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from tutelary.context import Governor
from tutelary.core.events import Event
from tutelary.core.fakes import FakeBus
from tutelary.core.ports import Memory, Policy, Provider, Sandbox, Tool
from tutelary.core.types import Allow, Decision, ToolCall
from tutelary.engine.budget import RunBudget
from tutelary.engine.hooks import HookEngine
from tutelary.engine.loop import Engine, EngineConfig
from tutelary.memory import MarkdownMemoryConfig, MarkdownProvider
from tutelary.providers.anthropic import AnthropicProvider
from tutelary.providers.openai_compatible import OpenAICompatibleProvider
from tutelary.runtime.toolbelt import Toolbelt


class _AllowAll:
    def check(self, call: ToolCall) -> Decision:
        return Allow()


class _NullMemory:
    async def recall(self, query: str, scope: Any) -> list[Any]:
        return []

    async def load_context(self, query: str, scope: Any) -> str:
        return ""


class Agent:
    """整船门面：构造即装配，run 即回合。

    全部组件可实例注入；memory / policy 缺省给空实现（引擎要求端口
    必须在位）。``report()`` 暴露治理内省（未接治理器时为 None）。
    """

    def __init__(
        self,
        *,
        provider: Provider,
        tools: Sequence[Tool] = (),
        policy: Policy | None = None,
        memory: Memory | None = None,
        # sandbox 保留装配面：沙箱由沙箱化工具（ExecTool）持有，门面不直接消费
        sandbox: Sandbox | None = None,
        governor: Governor | None = None,
        model: str = "default",
        agent_id: str = "agent",
        max_tool_hops: int = 8,
        bus: FakeBus | None = None,
        hooks: HookEngine | None = None,
        budget: RunBudget | None = None,
        result_inspector: Callable[[str], None] | None = None,
    ) -> None:
        self._bus = bus if bus is not None else FakeBus()
        self._result_inspector = result_inspector
        if memory is not None:
            setup = getattr(memory, "setup", None)
            if setup is not None:
                setup()
        self._engine = Engine(
            provider,
            Toolbelt(tools, result_inspector=self._result_inspector),
            policy if policy is not None else _AllowAll(),
            memory if memory is not None else _NullMemory(),
            config=EngineConfig(
                model=model, agent_id=agent_id, max_tool_hops=max_tool_hops, budget=budget
            ),
            hooks=hooks,
        )
        self._result_inspector = result_inspector
        self._governor = governor

    async def run(self, user_input: str, *, session_id: str = "default") -> AsyncIterator[Event]:
        """跑一个回合：治理 → 引擎循环，逐事件桥接 Bus 并原样产出。"""
        if self._governor is not None:
            enforced = await self._governor.enforce(self._engine.history(session_id))
            self._engine.replace_history(session_id, enforced.messages)
        async for event in self._engine.run(session_id, user_input):
            await self._bus.emit(event)
            yield event

    async def resume(
        self, session_id: str, *, decisions: Mapping[str, bool]
    ) -> AsyncIterator[Event]:
        """审批后从断点续跑：decisions 按 call.id 给出是否放行。

        停驻前的历史已治理过，续跑不重复 enforce；事件同样桥接 Bus。
        """
        async for event in self._engine.resume(session_id, decisions=decisions):
            await self._bus.emit(event)
            yield event

    def report(self) -> Any:
        """治理内省快照；未接治理器时返回 None。"""
        return self._governor.report() if self._governor is not None else None

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> Agent:
        """预设装配（docs/07 M3）：provider / memory / policy 三段映射。

        - provider.type：``openai-compatible``（base_url/api_key/model）或
          ``anthropic``；
        - memory.type：``markdown``（root）；
        - policy.allow：工具名名单（Allowlist）。
        tools / sandbox / governor 是实例，请走构造函数直接装配。
        """
        provider_cfg = dict(config["provider"])
        ptype = provider_cfg.pop("type")
        if ptype == "openai-compatible":
            provider: Provider = OpenAICompatibleProvider(**provider_cfg)  # type: ignore[arg-type]
        elif ptype == "anthropic":
            provider = AnthropicProvider(**provider_cfg)  # type: ignore[arg-type]
        else:
            raise ValueError(f"未知 provider 类型：{ptype!r}")

        memory: Memory | None = None
        memory_cfg = config.get("memory")
        if memory_cfg is not None:
            md = dict(memory_cfg)
            md.pop("type", None)
            memory = MarkdownProvider(
                FakeBus(), config=MarkdownMemoryConfig(root=Path(str(md.get("root", "."))))
            )

        policy: Policy | None = None
        policy_cfg = config.get("policy")
        if policy_cfg is not None:
            from tutelary.policy import Allowlist

            policy = Allowlist(tuple(policy_cfg["allow"]))  # type: ignore[union-attr, index-type]

        budget: RunBudget | None = None
        budget_cfg = config.get("budget")
        if budget_cfg is not None:
            budget = RunBudget(**budget_cfg)  # type: ignore[arg-type]

        return cls(
            provider=provider,
            memory=memory,
            policy=policy,
            model=str(provider_cfg.get("model", "default")),
            budget=budget,
        )
