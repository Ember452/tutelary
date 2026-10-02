"""Anthropic Messages API 的流式适配（/v1/messages，stream=true）。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from tutelary.core.events import LLMEvent, StreamText, ThinkingText, ToolUseEvent, UsageEvent
from tutelary.core.types import (
    LLMRequest,
    TextBlock,
    ToolCall,
    ToolResultBlock,
    ToolUseBlock,
    Usage,
)
from tutelary.providers.errors import ProviderError

_ANTHROPIC_VERSION = "2023-06-01"
_DEFAULT_MAX_TOKENS = 4096


def _text_of(message: Any) -> str:
    return "\n".join(block.text for block in message.content if isinstance(block, TextBlock))


def anthropic_messages(request: LLMRequest) -> list[dict[str, Any]]:
    """内核消息 → Anthropic messages；system 提升为顶层参数，工具结果进 tool_result 块。"""
    out: list[dict[str, Any]] = []
    for message in request.messages:
        if message.role == "system":
            continue
        if message.role == "tool":
            out.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": block.result.call_id,
                            "content": block.result.output,
                        }
                        for block in message.content
                        if isinstance(block, ToolResultBlock)
                    ],
                }
            )
            continue
        content: list[dict[str, Any]] = []
        for block in message.content:
            if isinstance(block, TextBlock):
                content.append({"type": "text", "text": block.text})
            elif isinstance(block, ToolUseBlock):
                content.append(
                    {
                        "type": "tool_use",
                        "id": block.call.id,
                        "name": block.call.name,
                        "input": dict(block.call.arguments),
                    }
                )
        out.append({"role": message.role, "content": content or [{"type": "text", "text": ""}]})
    return out


def anthropic_system(request: LLMRequest) -> str | None:
    parts = [_text_of(m) for m in request.messages if m.role == "system"]
    joined = "\n".join(part for part in parts if part)
    return joined or None


def anthropic_tools(request: LLMRequest) -> list[dict[str, Any]] | None:
    if not request.tools:
        return None
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "input_schema": dict(spec.parameters) or {"type": "object", "properties": {}},
        }
        for spec in request.tools
    ]


class AnthropicProvider:
    """Anthropic Provider：SSE 事件流按 content block 翻译。

    text_delta → StreamText；thinking_delta → ThinkingText；tool_use 块在
    content_block_stop 时以完整 input 发出 ToolUseEvent；计量来自
    message_start（输入）与 message_delta（输出）。
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        client: httpx.AsyncClient | None = None,
        timeout: float = 120.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._headers = {"x-api-key": api_key, "anthropic-version": _ANTHROPIC_VERSION}

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        system = anthropic_system(request)
        payload: dict[str, Any] = {
            "model": request.model if request.model != "default" else self._model,
            "messages": anthropic_messages(request),
            "max_tokens": request.max_output_tokens or _DEFAULT_MAX_TOKENS,
            "stream": True,
        }
        if system:
            payload["system"] = system
        tools = anthropic_tools(request)
        if tools:
            payload["tools"] = tools

        async with self._client.stream(
            "POST", f"{self._base_url}/v1/messages", json=payload, headers=self._headers
        ) as response:
            if response.status_code >= 400:
                body = (await response.aread()).decode("utf-8", errors="replace")
                raise ProviderError(f"HTTP {response.status_code}: {body[:500]}")
            async for event in self._translate(response.aiter_lines()):
                yield event

    async def _translate(self, lines: AsyncIterator[str]) -> AsyncIterator[LLMEvent]:
        input_tokens = 0
        output_tokens = 0
        tool_slot: dict[str, Any] | None = None
        async for line in lines:
            if not line.startswith("data:"):
                continue
            payload = json.loads(line[5:].strip())
            kind = payload.get("type")
            if kind == "message_start":
                input_tokens = payload.get("message", {}).get("usage", {}).get("input_tokens", 0)
            elif (
                kind == "content_block_start"
                and payload.get("content_block", {}).get("type") == "tool_use"
            ):
                block = payload["content_block"]
                tool_slot = {
                    "id": block.get("id", ""),
                    "name": block.get("name", ""),
                    "arguments": "",
                }
            elif kind == "content_block_delta":
                delta = payload.get("delta") or {}
                if delta.get("type") == "text_delta" and delta.get("text"):
                    yield StreamText(delta=delta["text"])
                elif delta.get("type") == "thinking_delta" and delta.get("thinking"):
                    yield ThinkingText(delta=delta["thinking"])
                elif delta.get("type") == "input_json_delta" and tool_slot is not None:
                    tool_slot["arguments"] += delta.get("partial_json", "")
            elif kind == "content_block_stop" and tool_slot is not None:
                yield ToolUseEvent(
                    call=ToolCall(
                        id=tool_slot["id"],
                        name=tool_slot["name"],
                        arguments=json.loads(tool_slot["arguments"] or "{}"),
                    )
                )
                tool_slot = None
            elif kind == "message_delta":
                output_tokens = payload.get("usage", {}).get("output_tokens", output_tokens)
            elif kind == "message_stop":
                yield UsageEvent(
                    usage=Usage(input_tokens=input_tokens, output_tokens=output_tokens)
                )
