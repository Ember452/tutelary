"""事件溯源异步生成器循环：一个回合从用户输入到最终回答。

引擎消费 Provider / Tool / Policy / Memory 四端口，只 **yield** 事件；
把事件桥接到 Bus 是组合根（runtime 门面）的职责。Suspend 判定会把
剩余工具调用停驻在会话里，``resume`` 从断点续跑。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from tutelary.core.events import (
    ErrorEvent,
    Event,
    LoopComplete,
    PermissionRequest,
    PermissionResponse,
    StreamText,
    ToolResultEvent,
    ToolUseEvent,
    TurnCommitted,
    TurnComplete,
    TurnStarted,
    UsageEvent,
)
from tutelary.core.lifecycle import Component, Disposable
from tutelary.core.ports import Memory, Policy, Provider, Tool
from tutelary.core.types import (
    Allow,
    Deny,
    LLMRequest,
    MemoryScope,
    Message,
    Suspend,
    TextBlock,
    ToolCall,
    ToolResult,
    ToolResultBlock,
    ToolSpec,
    ToolUseBlock,
    Usage,
)
from tutelary.engine.errors import NoPendingTurnError, ToolHopsExceededError


class Toolbelt(Protocol):
    """引擎消费的 Tool 实为"工具带"：specs() 聚合声明，execute() 按名路由。

    单提供者端口语义装不下 N 个工具——工具带由组合根组装
    （docs/plans/2026-10-02-m3-tasks.md §2）。
    """

    def specs(self) -> tuple[ToolSpec, ...]: ...

    async def execute(self, call: ToolCall) -> ToolResult: ...


@dataclass(frozen=True, slots=True)
class EngineConfig:
    """引擎配置：模型名、记忆归属的 agent、单回合工具调用轮数上限。"""

    model: str = "default"
    agent_id: str = "agent"
    max_tool_hops: int = 8

    @classmethod
    def model_validate(cls, data: dict[str, object]) -> EngineConfig:
        try:
            return cls(**data)  # type: ignore[arg-type]
        except TypeError as exc:
            raise ValueError(f"非法引擎配置字段：{exc}") from exc


@dataclass(slots=True)
class _Session:
    """会话驻留状态：事件可重建的消息序列 + Suspend 停驻的待批调用。"""

    messages: list[Message] = field(default_factory=list)
    pending: list[ToolCall] | None = None
    turn_seq: int = 0


class AgentLoop(Protocol):
    """引擎端口（M3 工作草案）：跑一个回合、断点续跑、供治理器读写历史。"""

    def run(self, session_id: str, user_input: str) -> AsyncIterator[Event]: ...

    def resume(self, session_id: str, *, decisions: Mapping[str, bool]) -> AsyncIterator[Event]: ...

    def history(self, session_id: str) -> list[Message]: ...

    def replace_history(self, session_id: str, messages: Sequence[Message]) -> None: ...


class Engine(Component):
    """参考循环：召回记忆 → 流式回答 → 策略判定 → 工具执行 → 结果回喂。

    事件溯源：``session.messages`` 全部由已产出的事件可重建；M3 驻留
    内存，持久化是后续工程（docs/plans/2026-10-02-m3-tasks.md §2）。
    """

    name = "engine"
    provides = (AgentLoop,)
    requires = (Provider, Tool, Policy, Memory)
    config_model = EngineConfig

    def __init__(
        self,
        provider: Provider,
        tool: Toolbelt,
        policy: Policy,
        memory: Memory,
        config: EngineConfig | None = None,
    ) -> None:
        self._provider = provider
        self._tool = tool
        self._policy = policy
        self._memory = memory
        self._config = config if config is not None else EngineConfig()
        self._sessions: dict[str, _Session] = {}

    def history(self, session_id: str) -> list[Message]:
        """会话当前消息序列（组合根治理用）；无会话时为空列表。"""
        return list(session.messages) if (session := self._sessions.get(session_id)) else []

    def replace_history(self, session_id: str, messages: Sequence[Message]) -> None:
        """整体替换会话消息——治理器压缩后由门面回写（ADR-0001 的组合根专用面）。"""
        self._sessions.setdefault(session_id, _Session()).messages = list(messages)

    async def run(self, session_id: str, user_input: str) -> AsyncIterator[Event]:
        """跑一个完整回合；产出 TurnStarted 起至 LoopComplete 止的事件流。"""
        yield TurnStarted(session_id=session_id, input=user_input)
        session = self._sessions.setdefault(session_id, _Session())
        scope = MemoryScope(agent_id=self._config.agent_id, session_id=session_id)
        recalled = await self._memory.load_context(user_input, scope)
        session.messages.append(Message(role="user", content=(TextBlock(text=user_input),)))
        prefix = [Message(role="system", content=(TextBlock(text=recalled),))] if recalled else []
        async for event in self._drive(session_id, session, prefix):
            yield event

    async def resume(
        self, session_id: str, *, decisions: Mapping[str, bool]
    ) -> AsyncIterator[Event]:
        """审批后从断点续跑：decisions 按 call.id 给出是否放行。"""
        session = self._sessions.get(session_id)
        if session is None or session.pending is None:
            raise NoPendingTurnError(f"会话 {session_id} 没有挂起中的回合")
        pending, session.pending = session.pending, None
        blocks: list[ToolResultBlock] = []
        for call in pending:
            approved = decisions.get(call.id, False)
            decision = Allow() if approved else Deny(reason="审批未通过")
            yield PermissionResponse(call=call, decision=decision)
            if isinstance(decision, Allow):
                result = await self._tool.execute(call)
            else:
                result = ToolResult(
                    call_id=call.id, output=f"被拒绝：{decision.reason}", is_error=True
                )
            yield ToolResultEvent(call=call, result=result)
            blocks.append(ToolResultBlock(result=result))
        session.messages.append(Message(role="tool", content=tuple(blocks)))
        async for event in self._drive(session_id, session, ()):
            yield event

    async def _drive(
        self, session_id: str, session: _Session, prefix: Sequence[Message]
    ) -> AsyncIterator[Event]:
        """主循环：请求 → 流式事件 → 工具判定与执行 → 结果回喂，直至无工具调用。"""
        try:
            total_usage = Usage()
            hops = 0
            while True:
                request = LLMRequest(
                    model=self._config.model,
                    messages=(*prefix, *session.messages),
                    tools=self._tool.specs(),
                )
                text_parts: list[str] = []
                calls: list[ToolCall] = []
                async for event in self._provider.stream(request):
                    if isinstance(event, StreamText):
                        text_parts.append(event.delta)
                    elif isinstance(event, ToolUseEvent):
                        calls.append(event.call)
                    elif isinstance(event, UsageEvent):
                        total_usage = Usage(
                            input_tokens=total_usage.input_tokens + event.usage.input_tokens,
                            output_tokens=total_usage.output_tokens + event.usage.output_tokens,
                        )
                    yield event

                assistant: list[Any] = []
                if text_parts:
                    assistant.append(TextBlock(text="".join(text_parts)))
                assistant.extend(ToolUseBlock(call=call) for call in calls)
                if assistant:
                    session.messages.append(Message(role="assistant", content=tuple(assistant)))

                if not calls:
                    turn_id = f"{session_id}-{session.turn_seq}"
                    session.turn_seq += 1
                    yield TurnCommitted(
                        turn_id=turn_id, text="".join(text_parts), session_id=session_id
                    )
                    yield TurnComplete(turn_id=turn_id, usage=total_usage)
                    yield LoopComplete(session_id=session_id)
                    return

                hops += 1
                if hops > self._config.max_tool_hops:
                    raise ToolHopsExceededError(
                        f"工具调用轮数超过上限 {self._config.max_tool_hops}"
                    )

                results: list[ToolResultBlock] = []
                suspended: list[ToolCall] = []
                for call in calls:
                    yield PermissionRequest(call=call)
                    decision = self._policy.check(call)
                    yield PermissionResponse(call=call, decision=decision)
                    if isinstance(decision, Suspend):
                        suspended.append(call)
                        continue
                    if isinstance(decision, Deny):
                        result = ToolResult(
                            call_id=call.id, output=f"被拒绝：{decision.reason}", is_error=True
                        )
                    else:
                        result = await self._tool.execute(call)
                    yield ToolResultEvent(call=call, result=result)
                    results.append(ToolResultBlock(result=result))

                if results:
                    session.messages.append(Message(role="tool", content=tuple(results)))
                if suspended:
                    # 断点停驻：已执行结果保位在消息里，剩余调用等待审批续跑
                    session.pending = suspended
                    return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            yield ErrorEvent(error=exc, phase=f"turn:{session_id}")

    def setup(self) -> Disposable | None:
        """引擎无自有副作用；记忆写路径由门面把事件桥接到 Bus 完成。"""
        return None
