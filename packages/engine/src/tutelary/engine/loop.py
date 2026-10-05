"""事件溯源异步生成器循环：一个回合从用户输入到最终回答。

引擎消费 Provider / Tool / Policy / Memory 四端口，只 **yield** 事件；
把事件桥接到 Bus 是组合根（runtime 门面）的职责。Suspend 判定会把
剩余工具调用停驻在会话里，``resume`` 从断点续跑。

FlowCoder 对齐 F1：八个生命周期点触发 HookEngine（可选协作者）；
RunBudget 四维预算按"收敛不击杀"处理——触顶后注入收敛消息并摘除
工具 schema，回合自然收尾。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from tutelary.core.events import (
    BudgetBreached,
    ErrorEvent,
    Event,
    HookEvent,
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
    Decision,
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
from tutelary.engine.budget import RunBudget, RunBudgetState
from tutelary.engine.errors import NoPendingTurnError, ToolHopsExceededError
from tutelary.engine.hooks import HookEngine, HookOutcome


class Toolbelt(Protocol):
    """引擎消费的 Tool 实为"工具带"：specs() 聚合声明，execute() 按名路由。

    单提供者端口语义装不下 N 个工具——工具带由组合根组装
    （docs/plans/2026-10-02-m3-tasks.md §2）。
    """

    def specs(self) -> tuple[ToolSpec, ...]: ...

    async def execute(self, call: ToolCall) -> ToolResult: ...


@dataclass(frozen=True, slots=True)
class EngineConfig:
    """引擎配置：模型名、记忆归属的 agent、单回合工具调用轮数上限、可选运行预算。"""

    model: str = "default"
    agent_id: str = "agent"
    max_tool_hops: int = 8
    budget: RunBudget | None = None

    @classmethod
    def model_validate(cls, data: Mapping[str, Any]) -> EngineConfig:
        data = dict(data)
        if isinstance(data.get("budget"), Mapping):
            data = {**data, "budget": RunBudget(**data["budget"])}
        try:
            return cls(**data)  # type: ignore[arg-type]
        except TypeError as exc:
            raise ValueError(f"非法引擎配置字段：{exc}") from exc


@dataclass(slots=True)
class _Session:
    """会话驻留状态：消息序列、Suspend 停驻的待批调用、预算记账。"""

    messages: list[Message] = field(default_factory=list)
    pending: list[ToolCall] | None = None
    turn_seq: int = 0
    budget_state: RunBudgetState | None = None
    converged: bool = False


class AgentLoop(Protocol):
    """引擎端口（M3 工作草案）：跑一个回合、断点续跑、供治理器读写历史。"""

    def run(self, session_id: str, user_input: str) -> AsyncIterator[Event]: ...

    def resume(self, session_id: str, *, decisions: Mapping[str, bool]) -> AsyncIterator[Event]: ...

    def history(self, session_id: str) -> list[Message]: ...

    def replace_history(self, session_id: str, messages: Sequence[Message]) -> None: ...


class Engine(Component):
    """参考循环：召回记忆 → 流式回答 → 策略判定 → 工具执行 → 结果回喂。

    事件溯源：``session.messages`` 全部由已产出的事件可重建；M3 驻留
    内存，持久化是后续工程。HookEngine 与 RunBudget 是可选协作者
    （FlowCoder 同款，非端口）——不注入即零行为。
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
        hooks: HookEngine | None = None,
    ) -> None:
        self._provider = provider
        self._tool = tool
        self._policy = policy
        self._memory = memory
        self._config = config if config is not None else EngineConfig()
        self._hooks = hooks
        self._sessions: dict[str, _Session] = {}

    def history(self, session_id: str) -> list[Message]:
        """会话当前消息序列（组合根治理用）；无会话时为空列表。"""
        return list(session.messages) if (session := self._sessions.get(session_id)) else []

    def replace_history(self, session_id: str, messages: Sequence[Message]) -> None:
        """整体替换会话消息——治理器压缩后由门面回写（ADR-0001 的组合根专用面）。"""
        self._sessions.setdefault(session_id, _Session()).messages = list(messages)

    async def run(self, session_id: str, user_input: str) -> AsyncIterator[Event]:
        """跑一个完整回合；产出 session_start / TurnStarted 起至 LoopComplete 止的事件流。"""
        is_new_session = session_id not in self._sessions
        session = self._sessions.setdefault(session_id, _Session())
        for receipt in self._hook_receipts(
            "session_start", await self._run_hooks("session_start", session_id=session_id)
        ):
            if is_new_session:
                yield receipt
        yield TurnStarted(session_id=session_id, input=user_input)
        for receipt in self._hook_receipts(
            "turn_start", await self._run_hooks("turn_start", session_id=session_id)
        ):
            yield receipt

        scope = MemoryScope(agent_id=self._config.agent_id, session_id=session_id)
        recalled = await self._memory.load_context(user_input, scope)
        session.messages.append(Message(role="user", content=(TextBlock(text=user_input),)))
        prefix = [Message(role="system", content=(TextBlock(text=recalled),))] if recalled else []
        async for event in self._drive(session_id, session, prefix, user_input=user_input):
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
        self,
        session_id: str,
        session: _Session,
        prefix: Sequence[Message],
        *,
        user_input: str = "",
    ) -> AsyncIterator[Event]:
        """主循环：预算检查 → pre_send → 请求 → 流式事件 → post_receive →
        工具判定与执行（pre_tool_use 可拒绝）→ 结果回喂，直至无工具调用。"""
        try:
            system_prefix = list(prefix)
            if self._config.budget is not None and session.budget_state is None:
                session.budget_state = RunBudgetState(self._config.budget)
            total_usage = Usage()
            hops = 0
            while True:
                if session.budget_state is not None:
                    session.budget_state.advance()
                    if not session.converged:
                        breach = session.budget_state.breach()
                        if breach is not None:
                            yield BudgetBreached(dimension=breach.dimension, reason=breach.reason)
                            session.messages.append(
                                Message(
                                    role="user",
                                    content=(
                                        TextBlock(
                                            text=session.budget_state.converge_message(breach)
                                        ),
                                    ),
                                )
                            )
                            session.converged = True

                send_outcome = await self._run_hooks(
                    "pre_send", session_id=session_id, input=user_input
                )
                for receipt in self._hook_receipts("pre_send", send_outcome):
                    yield receipt
                system_prefix.extend(
                    Message(role="system", content=(TextBlock(text=prompt),))
                    for prompt in send_outcome.prompts
                )

                request = LLMRequest(
                    model=self._config.model,
                    messages=(*system_prefix, *session.messages),
                    tools=() if session.converged else self._tool.specs(),
                )
                text_parts: list[str] = []
                calls: list[ToolCall] = []
                hop_usage = Usage()
                async for event in self._provider.stream(request):
                    if isinstance(event, StreamText):
                        text_parts.append(event.delta)
                    elif isinstance(event, ToolUseEvent):
                        calls.append(event.call)
                    elif isinstance(event, UsageEvent):
                        hop_usage = Usage(
                            input_tokens=hop_usage.input_tokens + event.usage.input_tokens,
                            output_tokens=hop_usage.output_tokens + event.usage.output_tokens,
                        )
                    yield event
                total_usage = Usage(
                    input_tokens=total_usage.input_tokens + hop_usage.input_tokens,
                    output_tokens=total_usage.output_tokens + hop_usage.output_tokens,
                )
                if session.budget_state is not None:
                    session.budget_state.record(hop_usage)

                receive_outcome = await self._run_hooks(
                    "post_receive",
                    session_id=session_id,
                    text="".join(text_parts),
                    usage=hop_usage,
                )
                for receipt in self._hook_receipts("post_receive", receive_outcome):
                    yield receipt

                assistant: list[Any] = []
                if text_parts:
                    assistant.append(TextBlock(text="".join(text_parts)))
                assistant.extend(ToolUseBlock(call=call) for call in calls)
                if assistant:
                    session.messages.append(Message(role="assistant", content=tuple(assistant)))

                if not calls:
                    async for event in self._turn_close(
                        session_id, session, text="".join(text_parts), usage=total_usage
                    ):
                        yield event
                    return

                hops += 1
                if hops > self._config.max_tool_hops:
                    raise ToolHopsExceededError(
                        f"工具调用轮数超过上限 {self._config.max_tool_hops}"
                    )

                # —— 判定相（串行）：Hook → 策略，事件序确定 ——
                decided: list[tuple[int, ToolCall, Decision]] = []
                rejected: dict[int, ToolResult] = {}
                suspended: list[ToolCall] = []
                for pos, call in enumerate(calls):
                    tool_outcome = await self._run_hooks(
                        "pre_tool_use",
                        session_id=session_id,
                        tool_name=call.name,
                        tool_id=call.id,
                        arguments=dict(call.arguments),
                    )
                    for receipt in self._hook_receipts("pre_tool_use", tool_outcome):
                        yield receipt
                    if tool_outcome.rejected:
                        # Hook 拒绝先于策略判定（FlowCoder 同序）：不执行、不判定
                        rejected[pos] = ToolResult(
                            call_id=call.id, output=tool_outcome.reject_reason, is_error=True
                        )
                        continue

                    yield PermissionRequest(call=call)
                    decision = self._policy.check(call)
                    yield PermissionResponse(call=call, decision=decision)
                    if isinstance(decision, Suspend):
                        # 整批阻塞（FlowCoder 同义）：当前及之后未判定的调用一并停驻
                        suspended = calls[pos:]
                        break
                    decided.append((pos, call, decision))

                # —— 执行相：并发安全的调用并行，其余串行——延迟重叠，事件序不变 ——
                outcomes: dict[int, ToolResult] = dict(rejected)
                spec_by_name = {spec.name: spec for spec in self._tool.specs()}
                tasks: dict[int, asyncio.Task[ToolResult]] = {}
                for pos, call, decision in decided:
                    if isinstance(decision, Deny):
                        outcomes[pos] = ToolResult(
                            call_id=call.id, output=f"被拒绝：{decision.reason}", is_error=True
                        )
                        continue
                    spec = spec_by_name.get(call.name)
                    if spec is not None and spec.is_concurrency_safe:
                        tasks[pos] = asyncio.create_task(self._tool.execute(call))
                for pos, call, decision in decided:
                    if pos in tasks or isinstance(decision, Deny):
                        continue
                    outcomes[pos] = await self._tool.execute(call)
                for pos, task in tasks.items():
                    outcomes[pos] = await task

                # —— 结果相：原顺序回执 + post_tool_use ——
                results: list[ToolResultBlock] = []
                stop = len(calls) - len(suspended)
                for pos, call in enumerate(calls[:stop]):
                    result = outcomes[pos]
                    yield ToolResultEvent(call=call, result=result)
                    results.append(ToolResultBlock(result=result))
                    post_outcome = await self._run_hooks(
                        "post_tool_use",
                        session_id=session_id,
                        tool_name=call.name,
                        tool_id=call.id,
                        output=result.output,
                    )
                    for receipt in self._hook_receipts("post_tool_use", post_outcome):
                        yield receipt

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

    async def _turn_close(
        self, session_id: str, session: _Session, *, text: str, usage: Usage
    ) -> AsyncIterator[Event]:
        """收尾序列：turn_end hook → TurnCommitted → TurnComplete →
        session_end hook → LoopComplete（FlowCoder 的结束相序）。"""
        for receipt in self._hook_receipts(
            "turn_end", await self._run_hooks("turn_end", session_id=session_id)
        ):
            yield receipt
        turn_id = f"{session_id}-{session.turn_seq}"
        session.turn_seq += 1
        yield TurnCommitted(turn_id=turn_id, text=text, session_id=session_id)
        yield TurnComplete(turn_id=turn_id, usage=usage)
        for receipt in self._hook_receipts(
            "session_end", await self._run_hooks("session_end", session_id=session_id)
        ):
            yield receipt
        yield LoopComplete(session_id=session_id)

    async def _run_hooks(self, event_name: str, **context: Any) -> HookOutcome:
        """触发一个生命周期点；Hook 异常被隔离为空结果（不阻断回合）。"""
        if self._hooks is None:
            return HookOutcome()
        try:
            return await self._hooks.run(event_name, context)
        except Exception as exc:
            return HookOutcome(errors=[str(exc)])

    def _hook_receipts(self, event_name: str, outcome: HookOutcome) -> list[HookEvent]:
        """把触发结果转成回执事件：正常 fire 按顺序，异常以 success=False 可观测。"""
        receipts = [
            HookEvent(hook_id=hook.name, event=event_name, success=True) for hook in outcome.fired
        ]
        receipts.extend(
            HookEvent(hook_id=event_name, event=event_name, output=error, success=False)
            for error in outcome.errors
        )
        return receipts

    def setup(self) -> Disposable | None:
        """引擎无自有副作用；记忆写路径由门面把事件桥接到 Bus 完成。"""
        return None
