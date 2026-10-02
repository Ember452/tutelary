"""only-providers：不依赖引擎，单独使用 providers 组件（M3 验收裁判）。

演示：OpenAI 兼容协议的流式适配（MockTransport 脚本化 SSE，全程离线）
包上 ResilientProvider 的重试/限流语义后对外行为不变。
跑法：``uv run python examples/only-providers.py``
"""

import asyncio
import json

import httpx

from tutelary.core.types import LLMRequest, Message, TextBlock
from tutelary.providers import OpenAICompatibleProvider, ResilientProvider


def _scripted_client() -> httpx.AsyncClient:
    chunks = [
        {"choices": [{"delta": {"content": "你好"}}]},
        {"choices": [{"delta": {"content": "，世界"}}]},
        {"choices": [], "usage": {"prompt_tokens": 8, "completion_tokens": 4}},
    ]
    body = "\n".join(f"data: {json.dumps(chunk)}" for chunk in chunks) + "\ndata: [DONE]\n"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def main() -> None:
    inner = OpenAICompatibleProvider(
        base_url="http://gateway.local",
        api_key="demo",
        model="demo-model",
        client=_scripted_client(),
    )
    provider = ResilientProvider(inner, max_attempts=2, backoff_seconds=0.0)
    request = LLMRequest(
        model="default", messages=(Message(role="user", content=(TextBlock(text="打个招呼"),)),)
    )
    async for event in provider.stream(request):
        kind = type(event).__name__
        detail = getattr(event, "delta", None) or getattr(event, "usage", "")
        print(f"[{kind}] {detail}")
    print("providers 离线流式 OK（SSE → 内核事件，韧性包装透明）")


if __name__ == "__main__":
    asyncio.run(main())
