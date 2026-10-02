"""FakeProvider：脚本回放顺序、请求记录与脚本耗尽。"""

import pytest

from tutelary.core.errors import TutelaryError
from tutelary.core.events import StreamText, UsageEvent
from tutelary.core.fakes import FakeProvider
from tutelary.core.types import LLMRequest, Message, TextBlock, Usage


def _request() -> LLMRequest:
    return LLMRequest(
        model="fake",
        messages=(Message(role="user", content=(TextBlock(text="hi"),)),),
    )


async def test_stream_replays_script_in_order():
    provider = FakeProvider(
        [
            StreamText(delta="a"),
            StreamText(delta="b"),
            UsageEvent(usage=Usage(input_tokens=1, output_tokens=2)),
        ],
        [
            StreamText(delta="c"),
            UsageEvent(usage=Usage(input_tokens=3, output_tokens=4)),
        ],
    )
    first = [event async for event in provider.stream(_request())]
    second = [event async for event in provider.stream(_request())]
    assert [event.delta for event in first if isinstance(event, StreamText)] == ["a", "b"]
    assert [event.delta for event in second if isinstance(event, StreamText)] == ["c"]
    assert isinstance(first[-1], UsageEvent)


async def test_requests_are_recorded_in_order():
    provider = FakeProvider([UsageEvent(usage=Usage())])
    async for _ in provider.stream(_request()):
        pass
    assert provider.requests == [_request()]


async def test_exhausted_script_raises_typed_error():
    provider = FakeProvider([UsageEvent(usage=Usage())])
    async for _ in provider.stream(_request()):
        pass
    with pytest.raises(TutelaryError):
        async for _ in provider.stream(_request()):
            pass
