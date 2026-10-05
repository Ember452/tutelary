"""工具执行编排（FlowCoder 对齐 F2）：并发安全并行批、串行保序、整批停驻。"""

import asyncio
import time
from collections.abc import Mapping

from tutelary.core.events import (
    LLMEvent,
    LoopComplete,
    PermissionResponse,
    StreamText,
    ToolResultEvent,
    ToolUseEvent,
)
from tutelary.core.fakes import FakeMemory, FakeProvider
from tutelary.core.types import (
    Allow,
    Decision,
    Deny,
    Suspend,
    ToolCall,
    ToolResult,
    ToolSpec,
)
from tutelary.engine.loop import Engine

_SESSION = "s1"


class _TimedBelt:
    """按名字声明执行耗时与并发安全性；记录每次执行的起止时刻。"""

    def __init__(self, plan: Mapping[str, tuple[float, bool]]) -> None:
        self._plan = dict(plan)
        self.intervals: dict[str, list[tuple[float, float]]] = {}

    def specs(self) -> tuple[ToolSpec, ...]:
        return tuple(
            ToolSpec(name=name, description="t", is_concurrency_safe=safe)
            for name, (_seconds, safe) in self._plan.items()
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        seconds, _safe = self._plan[call.name]
        started = time.monotonic()
        await asyncio.sleep(seconds)
        self.intervals.setdefault(call.name, []).append((started, time.monotonic()))
        return ToolResult(call_id=call.id, output=call.name)


class _AllowPolicy:
    def check(self, call: ToolCall) -> Decision:
        return Allow()


class _SuspendOnAsk:
    """ask_tool 一律挂起，其余放行。"""

    def check(self, call: ToolCall) -> Decision:
        if call.name == "ask_tool":
            return Suspend(prompt="审批")
        return Allow()


class _DenyA:
    def check(self, call: ToolCall) -> Decision:
        return Deny(reason="no") if call.name == "slow_a" else Allow()


def _call(cid: str, name: str) -> ToolUseEvent:
    return ToolUseEvent(call=ToolCall(id=cid, name=name))


def _engine(belt: _TimedBelt, turns: list[list[LLMEvent]], policy: object | None = None) -> Engine:
    provider = FakeProvider(*turns, [StreamText(delta="完成")])
    return Engine(provider, belt, policy or _AllowPolicy(), FakeMemory())  # type: ignore[arg-type]


def _overlaps(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


async def test_concurrency_safe_tools_run_in_parallel():
    belt = _TimedBelt({"slow_a": (0.25, True), "slow_b": (0.25, True)})
    engine = _engine(belt, [[_call("c1", "slow_a"), _call("c2", "slow_b")]])
    events = [e async for e in engine.run(_SESSION, "hi")]
    assert _overlaps(belt.intervals["slow_a"][0], belt.intervals["slow_b"][0])
    results = [e for e in events if isinstance(e, ToolResultEvent)]
    assert [r.result.output for r in results[:2]] == ["slow_a", "slow_b"]  # 结果仍按原序


async def test_unsafe_tools_run_serially():
    belt = _TimedBelt({"slow_a": (0.15, False), "slow_b": (0.15, False)})
    engine = _engine(belt, [[_call("c1", "slow_a"), _call("c2", "slow_b")]])
    async for _ in engine.run(_SESSION, "hi"):
        pass
    a = belt.intervals["slow_a"][0]
    b = belt.intervals["slow_b"][0]
    assert not _overlaps(a, b)  # 串行：区间不重叠


async def test_event_order_is_deterministic_in_mixed_batch():
    belt = _TimedBelt({"slow_a": (0.1, False), "slow_b": (0.1, True)})
    engine = _engine(belt, [[_call("c1", "slow_a"), _call("c2", "slow_b")]])
    events = [e async for e in engine.run(_SESSION, "hi")]
    sequence = [
        (type(e).__name__, e.call.id)
        for e in events
        if isinstance(e, (ToolUseEvent, PermissionResponse, ToolResultEvent))
    ]
    assert sequence == [
        ("ToolUseEvent", "c1"),
        ("ToolUseEvent", "c2"),
        ("PermissionResponse", "c1"),
        ("PermissionResponse", "c2"),
        ("ToolResultEvent", "c1"),
        ("ToolResultEvent", "c2"),
    ]
    assert isinstance(events[-1], LoopComplete)


async def test_suspend_blocks_the_whole_remaining_batch():
    belt = _TimedBelt({"slow_a": (0.0, True), "ask_tool": (0.0, True)})
    engine = _engine(
        belt,
        [[_call("c1", "slow_a"), _call("c2", "ask_tool")]],
        policy=_SuspendOnAsk(),
    )
    events = [e async for e in engine.run(_SESSION, "hi")]
    # 判定相在 ask_tool 处停驻：整批阻塞，其后调用未执行
    tool_results = [e for e in events if isinstance(e, ToolResultEvent)]
    assert [r.result.output for r in tool_results] == ["slow_a"]
    suspend_response = next(
        e for e in events if isinstance(e, PermissionResponse) and isinstance(e.decision, Suspend)
    )
    suspend_decision = suspend_response.decision
    assert isinstance(suspend_decision, Suspend)
    assert suspend_decision.prompt == "审批"
    # resume 放行 ask_tool，回合在续跑轮自然收尾
    resume_events = [e async for e in engine.resume(_SESSION, decisions={"c2": True})]
    resumed_results = [e for e in resume_events if isinstance(e, ToolResultEvent)]
    assert [r.result.output for r in resumed_results] == ["ask_tool"]
    assert isinstance(resume_events[-1], LoopComplete)


async def test_deny_keeps_batch_flow():
    belt = _TimedBelt({"slow_a": (0.0, True), "slow_b": (0.0, True)})
    engine = _engine(belt, [[_call("c1", "slow_a"), _call("c2", "slow_b")]], policy=_DenyA())
    events = [e async for e in engine.run(_SESSION, "hi")]
    results = [e for e in events if isinstance(e, ToolResultEvent)]
    assert results[0].result.is_error is True and "被拒绝" in results[0].result.output
    assert results[1].result.output == "slow_b"
