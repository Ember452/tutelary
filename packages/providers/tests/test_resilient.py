"""resilient.py：重试、故障转移、限流与"流中途不重试"语义。"""

import json
from collections.abc import AsyncIterator

import httpx
import pytest

from tutelary.core.events import LLMEvent, StreamText, ToolUseEvent
from tutelary.core.types import LLMRequest, Message, TextBlock
from tutelary.providers.errors import ProviderError
from tutelary.providers.openai_compatible import OpenAICompatibleProvider
from tutelary.providers.resilient import ResilientProvider

_REQUEST = LLMRequest(
    model="default", messages=(Message(role="user", content=(TextBlock(text="hi"),)),)
)


def _ok_provider(text: str) -> OpenAICompatibleProvider:
    chunks = [{"choices": [{"delta": {"content": text}}]}]
    body = "\n".join(f"data: {json.dumps(c)}" for c in chunks) + "\ndata: [DONE]\n"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OpenAICompatibleProvider(base_url="http://test", api_key="k", model="m", client=client)


class _FailingProvider:
    """前 fail_times 次抛传输错误，之后成功。"""

    def __init__(self, fail_times: int, fail_mid_stream: bool = False) -> None:
        self.fail_times = fail_times
        self.fail_mid_stream = fail_mid_stream
        self.calls = 0

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise httpx.ConnectError("连接被拒")
        yield StreamText(delta="ok")
        if self.fail_mid_stream:
            raise httpx.ReadError("流中途断开")


class _ScriptProvider:
    def __init__(self, events: list[LLMEvent]) -> None:
        self._events = events

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        for event in self._events:
            yield event


async def test_retries_then_succeeds_before_first_event():
    provider = ResilientProvider(
        _FailingProvider(fail_times=2), max_attempts=3, backoff_seconds=0.0
    )
    got = [event async for event in provider.stream(_REQUEST)]
    assert [e.delta for e in got if isinstance(e, StreamText)] == ["ok"]


async def test_fails_over_to_fallback_after_exhausted_retries():
    provider = ResilientProvider(
        _FailingProvider(fail_times=99),
        _ok_provider("来自备用"),
        max_attempts=2,
        backoff_seconds=0.0,
    )
    got = [event async for event in provider.stream(_REQUEST)]
    assert [e.delta for e in got if isinstance(e, StreamText)] == ["来自备用"]


async def test_mid_stream_failure_is_not_retried():
    provider = ResilientProvider(
        _FailingProvider(fail_times=0, fail_mid_stream=True),
        max_attempts=3,
        backoff_seconds=0.0,
    )
    with pytest.raises(ProviderError, match="不重试"):
        async for _ in provider.stream(_REQUEST):
            pass


async def test_all_providers_failing_raises_typed_error():
    provider = ResilientProvider(
        _FailingProvider(99), _FailingProvider(99), max_attempts=1, backoff_seconds=0.0
    )
    with pytest.raises(ProviderError, match="均失败"):
        async for _ in provider.stream(_REQUEST):
            pass


def test_max_attempts_must_be_positive():
    with pytest.raises(ValueError, match="max_attempts"):
        ResilientProvider(_ScriptProvider([]), max_attempts=0)


async def test_events_pass_through_unchanged():
    call = ToolUseEvent.__new__(ToolUseEvent)  # 占位事件，验证透传即可
    provider = ResilientProvider(_ScriptProvider([call]), max_attempts=1)
    got = [event async for event in provider.stream(_REQUEST)]
    assert got == [call]
