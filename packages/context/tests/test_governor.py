"""governor.py：enforce 三步、两条硬指标、事件广播与用量计量、可装配性。"""

from collections.abc import AsyncIterator

from tutelary.context import Budget, ContextGovernor, Governor
from tutelary.context.governor import OFFLOAD_THRESHOLD_TOKENS
from tutelary.core import (
    Assembler,
    Bus,
    CompactNotification,
    CompactStarted,
    FakeBus,
    FakeProvider,
    LLMEvent,
    Message,
    Provider,
    StreamText,
    TextBlock,
    ToolResult,
    ToolResultBlock,
    Usage,
    UsageEvent,
)
from tutelary.core.types import LLMRequest


class _ScriptedProvider:
    """装配器用的脚本化 Provider 组件：摘要轮固定回一段文本。"""

    name = "provider"
    provides = (Provider,)

    def __init__(self) -> None:
        summary_turn = [
            StreamText(delta="摘要：早期内容已折叠。"),
            UsageEvent(usage=Usage(input_tokens=10, output_tokens=2)),
        ]
        self._fake = FakeProvider(*([summary_turn] * 6))

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        async for event in self._fake.stream(request):
            yield event


class _BusHolder(FakeBus):
    name = "bus"
    provides = (Bus,)


def _turn(index: int) -> Message:
    role = "user" if index % 2 == 0 else "assistant"
    return Message(role=role, content=(TextBlock(text=f"轮次 {index}：{'细节。' * 150}"),))


async def test_enforce_under_budget_leaves_content_intact():
    governor = ContextGovernor(_ScriptedProvider(), FakeBus())
    messages = [_turn(0), _turn(1)]
    result = await governor.enforce(messages)
    assert result.messages == messages
    assert result.compacted is False
    assert result.offloaded == 0
    assert governor.report().measured["history"] > 0


async def test_enforce_compacts_over_budget_and_pins_must_survive():
    bus = FakeBus()
    started: list[CompactStarted] = []
    notifications: list[CompactNotification] = []

    async def on_started(event: CompactStarted) -> None:
        started.append(event)

    async def on_notification(event: CompactNotification) -> None:
        notifications.append(event)

    bus.observe(CompactStarted, on_started)
    bus.observe(CompactNotification, on_notification)

    governor = ContextGovernor(_ScriptedProvider(), bus)
    must_survive = "必须保留：回滚在周五"
    messages = [
        Message(role="user", content=(TextBlock(text=f"早会：{must_survive}"),)),
        *(_turn(i) for i in range(40)),
    ]
    result = await governor.enforce(messages, keep_substrings=[must_survive])
    assert result.compacted is True
    assert len(started) == 1
    assert len(notifications) == 1

    report = governor.report()
    assert report.measured["history"] <= report.budget.section_tokens("history")
    flat = "\n".join(
        block.text for m in result.messages for block in m.content if isinstance(block, TextBlock)
    )
    assert must_survive in flat


async def test_large_tool_results_are_offloaded_and_retrievable():
    governor = ContextGovernor(_ScriptedProvider(), FakeBus())
    big_output = "日志行 " * 3000
    messages = [
        Message(
            role="assistant",
            content=(ToolResultBlock(result=ToolResult(call_id="call-1", output=big_output)),),
        )
    ]
    result = await governor.enforce(messages)
    assert result.offloaded == 1
    flat = "\n".join(
        block.result.output
        for m in result.messages
        for block in m.content
        if isinstance(block, ToolResultBlock)
    )
    assert big_output not in flat
    assert "已卸载" in flat
    assert governor.offload_store.get("call-1") == big_output
    assert governor.report().offloads[0].tokens > OFFLOAD_THRESHOLD_TOKENS


async def test_usage_events_are_metered_via_bus():
    bus = FakeBus()
    governor = ContextGovernor(_ScriptedProvider(), bus)
    assert governor.setup() is not None
    await bus.emit(UsageEvent(usage=Usage(input_tokens=12, output_tokens=3)))
    report = governor.report()
    assert report.usage_input == 12
    assert report.usage_output == 3


async def test_governor_is_assemblable_with_fakes():
    tut = await Assembler().use(_ScriptedProvider).use(_BusHolder).use(ContextGovernor).assemble()
    governor = tut.get(Governor)
    assert isinstance(governor, ContextGovernor)
    result = await governor.enforce([_turn(0)])
    assert result.messages[0].role == "user"
    assert isinstance(governor.report().budget, Budget)
    await tut.shutdown()
