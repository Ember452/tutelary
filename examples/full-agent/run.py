"""full-agent：整船示例（M3 双裁判之一）——不改 core/组件一行跑通。

装配：脚本化 fake provider（一个工具调用回合 + 一个最终回答回合）+
ExecTool（SubprocessRuntime 沙箱执行）+ MarkdownProvider 记忆 + 组合
策略 + ContextGovernor 治理，全部挂在同一条 Bus 上。走完一整回合：
治理 → 召回注入 → 策略放行 → 沙箱执行 → 结果回喂 → 最终回答 →
事件桥接 Bus（TurnCommitted 落库）→ 治理瀑布。
跑法：``uv run python examples/full-agent/run.py``
"""

import asyncio
import sys
import tempfile
from pathlib import Path

from tutelary.context import Budget, ContextGovernor
from tutelary.core.events import StreamText, ToolUseEvent, UsageEvent
from tutelary.core.fakes import FakeBus, FakeProvider
from tutelary.core.types import MemoryScope, ToolCall, Usage
from tutelary.memory import MarkdownMemoryConfig, MarkdownProvider
from tutelary.policy import AllOf, Allowlist
from tutelary.runtime import Agent, ExecTool
from tutelary.sandbox import SubprocessRuntime

_SESSION = "s1"


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        bus = FakeBus()  # 整船一条总线：治理广播与记忆写路径共用
        provider = FakeProvider(
            [
                ToolUseEvent(
                    call=ToolCall(
                        id="call-1",
                        name="run_command",
                        arguments={"command": [sys.executable, "-c", "print('build ok')"]},
                    )
                )
            ],
            [
                StreamText(delta="构建命令已在沙箱执行，输出 build ok。"),
                UsageEvent(usage=Usage(input_tokens=120, output_tokens=18)),
            ],
        )
        memory = MarkdownProvider(bus, config=MarkdownMemoryConfig(root=Path(tmp) / "memory"))
        seed_scope = MemoryScope(agent_id="demo", session_id=_SESSION)
        memory.seed(seed_scope, "构建的项目惯例：命令必须经沙箱执行。")
        memory.setup()

        governor = ContextGovernor(
            FakeProvider([StreamText(delta="[治理摘要]"), UsageEvent(usage=Usage())]),
            bus,
            config=Budget(total=8000),
        )

        agent = Agent(
            provider=provider,
            tools=[ExecTool(SubprocessRuntime())],
            policy=AllOf(Allowlist(("run_command",))),
            memory=memory,
            governor=governor,
            bus=bus,
            agent_id="demo",
        )

        print("== full-agent 回合事件 ==")
        kinds: list[str] = []
        async for event in agent.run("构建", session_id=_SESSION):
            kind = type(event).__name__
            kinds.append(kind)
            print(f"  [{kind}]")

        assert "ToolResultEvent" in kinds, "工具未执行"
        assert "TurnCommitted" in kinds and "TurnComplete" in kinds
        hits = await memory.recall("构建", seed_scope)
        assert any("build ok" in hit.text for hit in hits), "TurnCommitted 未落库"
        print("== 双裁判·整船 OK：工具执行 + 事件桥接 + 记忆落库 ==")
        print(governor.report().render())


if __name__ == "__main__":
    asyncio.run(main())
