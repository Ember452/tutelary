"""anthropic.py：SSE 事件翻译与消息映射，MockTransport 离线验证。"""

import json

import httpx
import pytest

from tutelary.core.events import ToolUseEvent
from tutelary.core.types import (
    LLMRequest,
    Message,
    TextBlock,
    ToolCall,
    ToolResult,
    ToolResultBlock,
    ToolUseBlock,
)
from tutelary.providers.anthropic import AnthropicProvider, anthropic_messages, anthropic_system
from tutelary.providers.errors import ProviderError


def _sse(events: list[dict], status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        body = "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events)
        return httpx.Response(status, text=body, headers={"content-type": "text/event-stream"})

    return httpx.MockTransport(handler)


def _provider(events: list[dict], status: int = 200) -> AnthropicProvider:
    client = httpx.AsyncClient(transport=_sse(events, status))
    return AnthropicProvider(
        base_url="http://test", api_key="k", model="claude-test", client=client
    )


async def test_text_thinking_and_usage_translate_in_order():
    events = [
        {"type": "message_start", "message": {"usage": {"input_tokens": 20}}},
        {"type": "content_block_delta", "delta": {"type": "thinking_delta", "thinking": "想"}},
        {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "答"}},
        {"type": "message_delta", "usage": {"output_tokens": 4}},
        {"type": "message_stop"},
    ]
    request = LLMRequest(
        model="default", messages=(Message(role="user", content=(TextBlock(text="hi"),)),)
    )
    got = [e async for e in _provider(events).stream(request)]
    kinds = [type(e).__name__ for e in got]
    assert kinds == ["ThinkingText", "StreamText", "UsageEvent"]
    usage = got[-1].usage  # type: ignore[union-attr]
    assert usage.input_tokens == 20 and usage.output_tokens == 4


async def test_tool_use_block_emits_complete_call_at_block_stop():
    events = [
        {
            "type": "content_block_start",
            "content_block": {"type": "tool_use", "id": "t1", "name": "read_file"},
        },
        {
            "type": "content_block_delta",
            "delta": {"type": "input_json_delta", "partial_json": '{"pa'},
        },
        {
            "type": "content_block_delta",
            "delta": {"type": "input_json_delta", "partial_json": 'th": 1}'},
        },
        {"type": "content_block_stop"},
    ]
    request = LLMRequest(
        model="default", messages=(Message(role="user", content=(TextBlock(text="hi"),)),)
    )
    got = [e async for e in _provider(events).stream(request)]
    assert len(got) == 1 and isinstance(got[0], ToolUseEvent)
    assert got[0].call.name == "read_file"
    assert got[0].call.arguments == {"path": 1}


async def test_tool_results_map_to_tool_result_blocks():
    call = ToolCall(id="t1", name="read_file")
    request = LLMRequest(
        model="default",
        messages=(
            Message(role="system", content=(TextBlock(text="规则"),)),
            Message(role="assistant", content=(ToolUseBlock(call=call),)),
            Message(
                role="tool",
                content=(ToolResultBlock(result=ToolResult(call_id="t1", output="内容")),),
            ),
        ),
    )
    assert anthropic_system(request) == "规则"
    messages = anthropic_messages(request)
    assert messages[0]["role"] == "assistant" and messages[0]["content"][0]["type"] == "tool_use"
    assert messages[1]["content"][0] == {
        "type": "tool_result",
        "tool_use_id": "t1",
        "content": "内容",
    }


async def test_http_error_raises_typed_provider_error():
    request = LLMRequest(
        model="default", messages=(Message(role="user", content=(TextBlock(text="hi"),)),)
    )
    with pytest.raises(ProviderError, match="HTTP 401"):
        async for _ in _provider([], status=401).stream(request):
            pass
