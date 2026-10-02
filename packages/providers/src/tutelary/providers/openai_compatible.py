"""OpenAI 兼容协议的流式适配：任何实现 /chat/completions 的网关都能接。"""

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

_DEFAULT_MODEL = "default"


def _text_of(message: Any) -> str:
    return "\n".join(block.text for block in message.content if isinstance(block, TextBlock))


def openai_messages(request: LLMRequest) -> list[dict[str, Any]]:
    """把内核消息序列映射成 OpenAI chat 格式（role 语义一一对应）。"""
    out: list[dict[str, Any]] = []
    for message in request.messages:
        if message.role == "tool":
            for block in message.content:
                if isinstance(block, ToolResultBlock):
                    out.append(
                        {
                            "role": "tool",
                            "tool_call_id": block.result.call_id,
                            "content": block.result.output,
                        }
                    )
        elif message.role == "assistant":
            entry: dict[str, Any] = {"role": "assistant", "content": _text_of(message) or None}
            calls = [
                {
                    "id": block.call.id,
                    "type": "function",
                    "function": {
                        "name": block.call.name,
                        "arguments": json.dumps(dict(block.call.arguments)),
                    },
                }
                for block in message.content
                if isinstance(block, ToolUseBlock)
            ]
            if calls:
                entry["tool_calls"] = calls
            out.append(entry)
        else:
            out.append({"role": message.role, "content": _text_of(message)})
    return out


def openai_tools(request: LLMRequest) -> list[dict[str, Any]] | None:
    if not request.tools:
        return None
    return [
        {
            "type": "function",
            "function": {
                "name": spec.name,
                "description": spec.description,
                "parameters": dict(spec.parameters) or {"type": "object", "properties": {}},
            },
        }
        for spec in request.tools
    ]


def _translate_chunk(chunk: dict[str, Any], pending: dict[int, dict[str, str]]) -> list[LLMEvent]:
    """把一个 SSE chunk 翻译成内核事件；工具调用 fragment 先累积，流结束后补发。"""
    events: list[LLMEvent] = []
    choices = chunk.get("choices") or []
    if choices:
        delta = choices[0].get("delta") or {}
        reasoning = delta.get("reasoning_content") or delta.get("reasoning")
        if reasoning:
            events.append(ThinkingText(delta=reasoning))
        content = delta.get("content")
        if content:
            events.append(StreamText(delta=content))
        for fragment in delta.get("tool_calls") or []:
            index = fragment.get("index", 0)
            slot = pending.setdefault(index, {"id": "", "name": "", "arguments": ""})
            if fragment.get("id"):
                slot["id"] = fragment["id"]
            function = fragment.get("function") or {}
            if function.get("name"):
                slot["name"] = function["name"]
            if function.get("arguments"):
                slot["arguments"] += function["arguments"]
    usage = chunk.get("usage")
    if usage:
        events.append(
            UsageEvent(
                usage=Usage(
                    input_tokens=usage.get("prompt_tokens", 0),
                    output_tokens=usage.get("completion_tokens", 0),
                )
            )
        )
    return events


class OpenAICompatibleProvider:
    """OpenAI 兼容 Provider：base_url 可指向任意兼容实现（含本地网关）。

    流式事件顺序跟随上游原始序；工具调用因协议按 fragment 下发，在流
    结束时以完整 arguments 一次性发出（docs/plans/2026-10-02-m3-tasks.md
    §2 的已记录简化）。request.model 为 "default" 时使用构造时的模型。
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
        self._headers = {"Authorization": f"Bearer {api_key}"}

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        payload: dict[str, Any] = {
            "model": request.model if request.model != _DEFAULT_MODEL else self._model,
            "messages": openai_messages(request),
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        tools = openai_tools(request)
        if tools:
            payload["tools"] = tools

        pending: dict[int, dict[str, str]] = {}
        async with self._client.stream(
            "POST", f"{self._base_url}/chat/completions", json=payload, headers=self._headers
        ) as response:
            if response.status_code >= 400:
                body = (await response.aread()).decode("utf-8", errors="replace")
                raise ProviderError(f"HTTP {response.status_code}: {body[:500]}")
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                for event in _translate_chunk(json.loads(data), pending):
                    yield event

        for index in sorted(pending):
            slot = pending[index]
            yield ToolUseEvent(
                call=ToolCall(
                    id=slot["id"] or f"call-{index}",
                    name=slot["name"],
                    arguments=json.loads(slot["arguments"] or "{}"),
                )
            )
