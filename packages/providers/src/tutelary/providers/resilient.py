"""ResilientProvider：重试、故障转移与并发上限的 Provider 包装。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from tutelary.core.ports import Provider
from tutelary.core.types import LLMRequest
from tutelary.providers.errors import ProviderError


class ResilientProvider:
    """主 Provider 失败时按退避重试，重试穷尽后沿备用链故障转移。

    重试语义（刻意保守，docs/plans/2026-10-02-m3-tasks.md §2）：只在
    **尚未产出任何事件**的失败上重试或转移——流中途失败重试会让调用方
    收到重复输出，宁可上抛 ProviderError。取消（CancelledError）永远
    原样放行（docs/04 §2）。``max_concurrency`` 用信号量给整条链限流。
    """

    def __init__(
        self,
        primary: Provider,
        *fallbacks: Provider,
        max_attempts: int = 3,
        backoff_seconds: float = 0.5,
        max_concurrency: int = 8,
    ) -> None:
        if max_attempts < 1:
            raise ValueError(f"max_attempts 必须 >= 1，得到 {max_attempts}")
        self._chain = (primary, *fallbacks)
        self._max_attempts = max_attempts
        self._backoff_seconds = backoff_seconds
        self._gate = asyncio.Semaphore(max_concurrency)

    async def stream(self, request: LLMRequest) -> AsyncIterator[object]:
        async with self._gate:
            last_error: Exception | None = None
            for provider in self._chain:
                for attempt in range(self._max_attempts):
                    emitted = False
                    try:
                        async for event in provider.stream(request):
                            emitted = True
                            yield event
                        return
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        last_error = exc
                        if emitted:
                            raise ProviderError(f"流中途失败，已产出事件不重试：{exc}") from exc
                        if attempt + 1 < self._max_attempts and self._backoff_seconds > 0:
                            await asyncio.sleep(self._backoff_seconds * (2**attempt))
            raise ProviderError(
                f"全部 {len(self._chain)} 个 provider 均失败：{last_error}"
            ) from last_error
