"""openai_compatible.py：SSE 翻译与消息映射，全部经 MockTransport 离线验证。"""

import json

import httpx
import pytest

from tutelary.core.events import StreamText, ThinkingText, UsageEvent
from tutelary.core.types import (
    LLMRequest,
    Message,
    TextBlock,
    ToolCall,
    ToolResult,
    ToolResultBlock,
    ToolUseBlock,
)
from tutelary.providers.errors import ProviderError
from tutelary.providers.openai_compatible import OpenAICompatibleProvider


def _transport(chunks: list[dict], status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        body = "\n".join(f"data: {json.dumps(chunk)}" for chunk in chunks) + "\ndata: [DONE]\n"
        return httpx.Response(status, text=body, headers={"content-type": "text/event-stream"})

    return httpx.MockTransport(handler)


def _provider(chunks: list[dict], status: int = 200) -> OpenAICompatibleProvider:
    client = httpx.AsyncClient(transport=_transport(chunks, status))
    return OpenAICompatibleProvider(
        base_url="http://test", api_key="k", model="gpt-test", client=client
    )


def _request() -> LLMRequest:
    return LLMRequest(
        model="default",
        messages=(Message(role="user", content=(TextBlock(text="hi"),)),),
    )


async def test_text_and_usage_are_translated_in_order():
    chunks = [
        {"choices": [{"delta": {"content": "你"}}]},
        {"choices": [{"delta": {"content": "好"}}]},
        {"choices": [], "usage": {"prompt_tokens": 12, "completion_tokens": 3}},
    ]
    events = [event async for event in _provider(chunks).stream(_request())]
    assert [type(e).__name__ for e in events] == ["StreamText", "StreamText", "UsageEvent"]
    assert isinstance(events[2], UsageEvent)
    assert events[2].usage.total_tokens == 15


async def test_reasoning_content_maps_to_thinking_text():
    chunks = [
        {"choices": [{"delta": {"reasoning_content": "想一想"}}]},
        {"choices": [{"delta": {"content": "答"}}]},
    ]
    events = [event async for event in _provider(chunks).stream(_request())]
    assert isinstance(events[0], ThinkingText)
    assert isinstance(events[1], StreamText)


async def test_tool_call_fragments_are_accumulated_and_emitted_complete():
    chunks = [
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "c1",
                                "function": {"name": "read_file", "arguments": '{"pa'},
                            }
                        ]
                    }
                }
            ]
        },
        {
            "choices": [
                {"delta": {"tool_calls": [{"index": 0, "function": {"arguments": 'th": "a.md"}'}}]}}
            ]
        },
        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
    ]
    events = [event async for event in _provider(chunks).stream(_request())]
    assert len(events) == 1
    call = events[0].call  # type: ignore[union-attr]
    assert call.id == "c1"
    assert call.name == "read_file"
    assert call.arguments == {"path": "a.md"}


async def test_history_with_tool_results_maps_to_openai_shape():
    call = ToolCall(id="c1", name="read_file", arguments={"path": "a.md"})
    request = LLMRequest(
        model="default",
        messages=(
            Message(role="system", content=(TextBlock(text="你是助手"),)),
            Message(role="assistant", content=(ToolUseBlock(call=call),)),
            Message(
                role="tool",
                content=(ToolResultBlock(result=ToolResult(call_id="c1", output="内容")),),
            ),
        ),
    )
    sent = json.loads(json.dumps(_request_messages(request)))
    assert sent[0] == {"role": "system", "content": "你是助手"}
    assert sent[1]["tool_calls"][0]["function"]["arguments"] == '{"path": "a.md"}'
    assert sent[2] == {"role": "tool", "tool_call_id": "c1", "content": "内容"}


def _request_messages(request: LLMRequest) -> list[dict]:
    from tutelary.providers.openai_compatible import openai_messages

    return openai_messages(request)


async def test_http_error_raises_typed_provider_error():
    with pytest.raises(ProviderError, match="HTTP 500"):
        async for _ in _provider([], status=500).stream(_request()):
            pass


async def test_default_model_falls_back_to_configured_model():
    seen_models: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_models.append(json.loads(request.content)["model"])
        return httpx.Response(200, text="data: [DONE]\n")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(
        base_url="http://test", api_key="k", model="cfg-model", client=client
    )
    async for _ in provider.stream(_request()):
        pass
    assert seen_models == ["cfg-model"]
