"""FakeProvider：Provider 端口的脚本化假实现——离线测试与 only-* 的标准供给。"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

from tutelary.core.errors import TutelaryError
from tutelary.core.events import LLMEvent
from tutelary.core.types import LLMRequest


class FakeProvider:
    """按构造时给定的脚本逐轮流式回放；脚本耗尽后再调用即抛 TutelaryError。

    Usage 必发是 Provider 契约（docs/04 §2）——由脚本作者保证，fake 只
    负责忠实回放。已收到的请求按序记录在 ``requests``，供断言使用。
    """

    def __init__(self, *turns: Sequence[LLMEvent]) -> None:
        self._turns = [list(turn) for turn in turns]
        self._cursor = 0
        self.requests: list[LLMRequest] = []

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        self.requests.append(request)
        if self._cursor >= len(self._turns):
            raise TutelaryError("FakeProvider 脚本耗尽：stream 调用次数多于提供的轮数")
        for event in self._turns[self._cursor]:
            yield event
        self._cursor += 1
