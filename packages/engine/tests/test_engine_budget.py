"""RunBudget：四维触顶收敛（不击杀）、schema 摘除与会话连续性。"""

import pytest

from tutelary.core.events import BudgetBreached, LLMEvent, StreamText, ToolUseEvent, UsageEvent
from tutelary.core.fakes import FakeMemory, FakeProvider
from tutelary.core.types import (
    Allow,
    Decision,
    Suspend,
    ToolCall,
    ToolResult,
    ToolSpec,
    Usage,
)
from tutelary.engine.budget import RunBudget
from tutelary.engine.loop import Engine, EngineConfig

_SESSION = "s1"


class _RecordingBelt:
    def __init__(self) -> None:
        self.executed: list[ToolCall] = []

    def specs(self) -> tuple[ToolSpec, ...]:
        return (ToolSpec(name="read_file", description="t"),)

    async def execute(self, call: ToolCall) -> ToolResult:
        self.executed.append(call)
        return ToolResult(call_id=call.id, output="内容")


class _AllowPolicy:
    def check(self, call: ToolCall) -> Decision:
        return Allow()


class _SuspendPolicy:
    def check(self, call: ToolCall) -> Decision:
        return Suspend(prompt="审批")


def _engine(budget: RunBudget, provider: FakeProvider) -> Engine:
    return Engine(
        provider,
        _RecordingBelt(),
        _AllowPolicy(),
        FakeMemory(),
        config=EngineConfig(budget=budget),
    )


def _tool_turn() -> list[LLMEvent]:
    return [ToolUseEvent(call=ToolCall(id="c1", name="read_file"))]


def test_budget_requires_at_least_one_limit():
    with pytest.raises(ValueError, match="至少要设置一项上限"):
        RunBudget()


async def test_turns_breach_converges_instead_of_killing():
    provider = FakeProvider(_tool_turn(), [StreamText(delta="收敛回答")])
    engine = _engine(RunBudget(max_turns=1), provider)
    events = [e async for e in engine.run(_SESSION, "hi")]

    breached = [e for e in events if isinstance(e, BudgetBreached)]
    assert len(breached) == 1 and breached[0].dimension == "turns"
    # 收敛后工具 schema 被摘除：第二个请求 tools 为空
    assert provider.requests[1].tools == ()
    assert [type(e).__name__ for e in events][-1] == "LoopComplete"  # 自然收尾


async def test_tokens_breach_uses_cumulative_usage():
    provider = FakeProvider(
        [*_tool_turn(), UsageEvent(usage=Usage(input_tokens=5000, output_tokens=0))],
        [StreamText(delta="收敛回答")],
    )
    engine = _engine(RunBudget(max_total_tokens=100), provider)
    events = [e async for e in engine.run(_SESSION, "hi")]
    breached = [e for e in events if isinstance(e, BudgetBreached)]
    assert len(breached) == 1 and breached[0].dimension == "tokens"
    assert provider.requests[1].tools == ()


async def test_cost_breach_needs_pricing():
    provider = FakeProvider(
        [*_tool_turn(), UsageEvent(usage=Usage(input_tokens=200, output_tokens=0))],
        [StreamText(delta="收敛回答")],
    )
    engine = _engine(RunBudget(max_cost_usd=1.0, input_price_per_m=10_000), provider)
    events = [e async for e in engine.run(_SESSION, "hi")]
    breached = [e for e in events if isinstance(e, BudgetBreached)]
    assert len(breached) == 1 and breached[0].dimension == "cost"


async def test_seconds_breach_fires_immediately():
    provider = FakeProvider([StreamText(delta="直接收敛")])
    engine = _engine(RunBudget(max_seconds=0.0), provider)
    events = [e async for e in engine.run(_SESSION, "hi")]
    breached = [e for e in events if isinstance(e, BudgetBreached)]
    assert len(breached) == 1 and breached[0].dimension == "seconds"
    assert [type(e).__name__ for e in events][-1] == "LoopComplete"


async def test_no_breach_when_budget_generous():
    provider = FakeProvider([StreamText(delta="正常")])
    engine = _engine(RunBudget(max_seconds=3600.0), provider)
    events = [e async for e in engine.run(_SESSION, "hi")]
    assert not [e for e in events if isinstance(e, BudgetBreached)]


async def test_budget_state_continues_across_suspend_resume():
    provider = FakeProvider(_tool_turn(), [StreamText(delta="续跑后收敛")])
    engine = Engine(
        provider,
        _RecordingBelt(),
        _SuspendPolicy(),
        FakeMemory(),
        config=EngineConfig(budget=RunBudget(max_turns=1)),
    )
    async for _ in engine.run(_SESSION, "hi"):  # 挂起（Suspend 策略）
        pass
    resume_events = [e async for e in engine.resume(_SESSION, decisions={"c1": True})]
    # 迭代数跨挂起连续：resume 的循环即触顶收敛
    assert any(isinstance(e, BudgetBreached) for e in resume_events)
    assert [type(e).__name__ for e in resume_events][-1] == "LoopComplete"
