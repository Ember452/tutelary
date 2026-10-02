"""only-core：不依赖任何组件包，只用 core 与 fakes 跑通"hello 装配"。

这是内核自己的 only-*（M0 验收第 4 条）：装配、依赖注入、事件流、
订阅随 shutdown 回滚——全程离线。跑法：``uv run python examples/only-core.py``
"""

import asyncio
from typing import Protocol

from tutelary.core import Assembler, Bus, Component, Disposable, FakeBus, TurnStarted


class BusProvider(FakeBus):
    """把 FakeBus 直接暴露成组件——组件即端口实现。"""

    name = "bus"
    provides = (Bus,)


class GreeterPort(Protocol):
    """组合根与测试取回 Greeter 状态用的窄端口。"""

    @property
    def greetings(self) -> list[str]: ...


class Greeter(Component):
    """订阅 TurnStarted 的最小事件消费者。"""

    name = "greeter"
    provides = (GreeterPort,)
    requires = (Bus,)

    def __init__(self, bus: Bus) -> None:
        self.greetings: list[str] = []
        self._bus = bus

    def setup(self) -> Disposable | None:
        async def on_turn(event: TurnStarted) -> None:
            self.greetings.append(f"hello, {event.input}")

        # 返回的 Disposable 登记进 effect 栈：shutdown 时自动退订
        return self._bus.observe(TurnStarted, on_turn)


async def main() -> None:
    tut = await Assembler().use(BusProvider).use(Greeter).assemble()
    bus = tut.get(Bus)
    greeter = tut.get(GreeterPort)

    await bus.emit(TurnStarted(session_id="s1", input="world"))
    assert greeter.greetings == ["hello, world"]
    print("装配 + 依赖注入 + 事件流 OK：", greeter.greetings)

    await tut.shutdown()
    await bus.emit(TurnStarted(session_id="s1", input="nobody"))
    assert greeter.greetings == ["hello, world"]
    print("shutdown 订阅回滚 OK：", greeter.greetings)


if __name__ == "__main__":
    asyncio.run(main())
