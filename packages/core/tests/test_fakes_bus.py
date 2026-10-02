"""FakeBus：observe 扇出与失败隔离、intercept 链改写/否决、退订。"""

import pytest

from tutelary.core.errors import BusContractError
from tutelary.core.events import StreamText, ThinkingText, TurnStarted
from tutelary.core.fakes import FakeBus
from tutelary.core.lifecycle import run_disposable


async def test_observe_fans_out_to_all_handlers():
    bus = FakeBus()
    seen_a: list[str] = []
    seen_b: list[str] = []

    async def a(event: TurnStarted) -> None:
        seen_a.append(event.input)

    async def b(event: TurnStarted) -> None:
        seen_b.append(event.input)

    bus.observe(TurnStarted, a)
    bus.observe(TurnStarted, b)
    result = await bus.emit(TurnStarted(session_id="s", input="hi"))
    assert seen_a == ["hi"]
    assert seen_b == ["hi"]
    assert result.input == "hi"


async def test_observer_failure_is_isolated():
    bus = FakeBus()
    seen: list[str] = []

    async def broken(event: TurnStarted) -> None:
        raise RuntimeError("observer blew up")

    async def healthy(event: TurnStarted) -> None:
        seen.append(event.input)

    bus.observe(TurnStarted, broken)
    bus.observe(TurnStarted, healthy)
    await bus.emit(TurnStarted(session_id="s", input="hi"))
    assert seen == ["hi"]


async def test_intercept_rewrites_event_before_observers():
    bus = FakeBus()
    seen: list[str] = []

    async def rewrite(event: TurnStarted) -> TurnStarted:
        return TurnStarted(session_id=event.session_id, input="rewritten")

    async def observer(event: TurnStarted) -> None:
        seen.append(event.input)

    bus.intercept(TurnStarted, rewrite)
    bus.observe(TurnStarted, observer)
    result = await bus.emit(TurnStarted(session_id="s", input="original"))
    assert seen == ["rewritten"]
    assert result.input == "rewritten"


async def test_intercept_veto_hides_event_from_observers():
    bus = FakeBus()
    seen: list[str] = []

    async def veto(event: TurnStarted) -> TurnStarted | None:
        return None

    async def observer(event: TurnStarted) -> None:
        seen.append(event.input)

    bus.intercept(TurnStarted, veto)
    bus.observe(TurnStarted, observer)
    result = await bus.emit(TurnStarted(session_id="s", input="hi"))
    assert seen == []
    assert result.input == "hi"


async def test_intercept_is_rejected_for_stream_deltas():
    bus = FakeBus()

    async def handler(event: StreamText) -> StreamText | None:
        return None

    with pytest.raises(BusContractError):
        bus.intercept(StreamText, handler)
    with pytest.raises(BusContractError):
        bus.intercept(ThinkingText, handler)  # type: ignore[arg-type]


async def test_dispose_unsubscribes_and_is_repeatable():
    bus = FakeBus()
    seen: list[str] = []

    async def observer(event: TurnStarted) -> None:
        seen.append(event.input)

    dispose = bus.observe(TurnStarted, observer)
    await run_disposable(dispose)
    await run_disposable(dispose)  # 重复退订安全
    await bus.emit(TurnStarted(session_id="s", input="hi"))
    assert seen == []


async def test_intercepts_run_in_registration_order():
    bus = FakeBus()
    order: list[str] = []

    async def first(event: TurnStarted) -> TurnStarted:
        order.append("first")
        return event

    async def second(event: TurnStarted) -> TurnStarted:
        order.append("second")
        return event

    bus.intercept(TurnStarted, second)
    bus.intercept(TurnStarted, first)
    await bus.emit(TurnStarted(session_id="s", input="hi"))
    assert order == ["second", "first"]


async def test_emit_without_handlers_returns_event_unchanged():
    bus = FakeBus()
    event = TurnStarted(session_id="s", input="hi")
    assert await bus.emit(event) is event
