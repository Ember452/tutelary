"""FakeBus：Bus 端口的内存参考实现，随契约发布（docs/08 §2）。

实现即 03 §3 的契约本体：observe 并发扇出、失败隔离；intercept 依注册
顺序成链、可改写可否决；emit 先拦截后扇出。流式增量事件的拦截在注册时
直接拒绝——04 §3 的硬规则在这里强制，而不是靠约定。
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import cast

from tutelary.core.errors import BusContractError
from tutelary.core.events import Event, StreamText, ThinkingText
from tutelary.core.lifecycle import Disposable

type _Observer = Callable[[Event], Awaitable[None]]
type _Interceptor = Callable[[Event], Awaitable[Event | None]]

_INTERCEPT_FORBIDDEN: tuple[type[Event], ...] = (StreamText, ThinkingText)


class FakeBus:
    """内存事件总线：observers / interceptors 的注册表 + emit 管线。"""

    def __init__(self) -> None:
        self._observers: dict[type[Event], list[_Observer]] = {}
        self._interceptors: dict[type[Event], list[_Interceptor]] = {}

    def observe[E: Event](self, et: type[E], handler: Callable[[E], Awaitable[None]]) -> Disposable:
        """扇出订阅；返回的 Disposable 调用后即退订，可安全重复调用。"""
        return self._register(self._observers, et, cast(_Observer, handler))

    def intercept[E: Event](
        self, et: type[E], handler: Callable[[E], Awaitable[E | None]]
    ) -> Disposable:
        """拦截订阅；流式增量事件（StreamText/ThinkingText）在注册时拒绝。"""
        if et in _INTERCEPT_FORBIDDEN:
            raise BusContractError(f"{et.__name__} 是流式增量事件，不设拦截（04 §3）")
        return self._register(self._interceptors, et, cast(_Interceptor, handler))

    async def emit[E: Event](self, event: E) -> E:
        """先按注册顺序跑 intercept 链，再对最终事件并发扇出 observe。"""
        current: Event = event
        for interceptor in self._interceptors.get(type(event), ()):
            replacement = await interceptor(current)
            if replacement is None:
                # 否决：链上已有的改写一并作废，观察者不可见
                return event
            current = replacement
        observers = self._observers.get(type(current), ())
        if observers:
            # 失败隔离：观察者路径的异常不影响发射方与其他观察者（03 §3）
            await asyncio.gather(
                *(observer(current) for observer in observers), return_exceptions=True
            )
        return cast(E, current)

    def _register[H](
        self, table: dict[type[Event], list[H]], et: type[Event], handler: H
    ) -> Disposable:
        handlers = table.setdefault(et, [])
        handlers.append(handler)

        def dispose() -> None:
            # 按身份移除：同一函数注册两次时只退订一次
            for index, registered in enumerate(handlers):
                if registered is handler:
                    del handlers[index]
                    break

        return dispose
