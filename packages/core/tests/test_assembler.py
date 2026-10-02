"""assembler.py：依赖注入、四种 fail-fast 错误与装配失败回滚。"""

from typing import Any

import pytest

from tutelary.core.assembler import Assembler
from tutelary.core.errors import (
    CircularRequirementError,
    ConfigValidationError,
    DuplicatePortError,
    MissingPortError,
)
from tutelary.core.events import Bus, TurnStarted
from tutelary.core.fakes import FakeBus
from tutelary.core.lifecycle import Component, Disposable


class P1:
    """测试用端口。"""


class P2:
    """测试用端口。"""


class BusProvider(FakeBus):
    """提供 Bus 端口的最小组件：组件即端口实现。"""

    name = "bus"
    provides = (Bus,)


class NeedsBus(Component):
    """订阅 TurnStarted 的消费组件；同时提供 P1 供测试取回实例。"""

    name = "needs-bus"
    provides = (P1,)
    requires = (Bus,)

    def __init__(self, bus: FakeBus) -> None:
        self.bus = bus
        self.seen: list[str] = []

    def setup(self) -> Disposable | None:
        async def on_turn(event: TurnStarted) -> None:
            self.seen.append(event.input)

        return self.bus.observe(TurnStarted, on_turn)


async def test_assemble_wires_dependencies_and_runs_setup():
    tut = await Assembler().use(BusProvider).use(NeedsBus).assemble()
    bus = tut.get(Bus)
    needs = tut.get(P1)
    assert isinstance(needs, NeedsBus)
    assert needs.bus is bus
    await bus.emit(TurnStarted(session_id="s", input="hello"))
    assert needs.seen == ["hello"]
    await tut.shutdown()


async def test_assemble_is_order_independent():
    tut = await Assembler().use(NeedsBus).use(BusProvider).assemble()
    assert isinstance(tut.get(Bus), FakeBus)
    await tut.shutdown()


async def test_missing_port_raises():
    class Lonely(Component):
        name = "lonely"
        requires = (P2,)

    with pytest.raises(MissingPortError, match="P2"):
        await Assembler().use(Lonely).assemble()


async def test_duplicate_port_raises():
    class AltBus(FakeBus):
        name = "alt-bus"
        provides = (Bus,)

    with pytest.raises(DuplicatePortError, match="Bus"):
        await Assembler().use(BusProvider).use(AltBus).assemble()


async def test_circular_requirement_raises():
    class CompA(Component):
        name = "a"
        provides = (P1,)
        requires = (P2,)

    class CompB(Component):
        name = "b"
        provides = (P2,)
        requires = (P1,)

    with pytest.raises(CircularRequirementError, match="a"):
        await Assembler().use(CompA).use(CompB).assemble()


class DuckConfig:
    """鸭子配置模型：有 model_validate(dict) 即可，无需 pydantic。"""

    def __init__(self, size: int) -> None:
        self.size = size

    @classmethod
    def model_validate(cls, data: dict[str, Any]) -> "DuckConfig":
        if "size" not in data:
            raise ValueError("size 必填")
        return cls(size=int(data["size"]))


class Sized(Component):
    name = "sized"
    provides = (P1,)
    config_model = DuckConfig

    def __init__(self, *, config: DuckConfig | None = None) -> None:
        self.config = config


async def test_config_is_validated_and_injected():
    tut = await Assembler().use(Sized, config={"size": 3}).assemble()
    sized = tut.get(P1)
    assert isinstance(sized, Sized)
    assert isinstance(sized.config, DuckConfig)
    assert sized.config.size == 3
    await tut.shutdown()


async def test_config_validation_failure_raises():
    class BadModel:
        @classmethod
        def model_validate(cls, data: dict[str, Any]) -> Any:
            raise ValueError("nope")

    class Picky(Component):
        name = "picky"
        config_model = BadModel

    with pytest.raises(ConfigValidationError, match="picky"):
        await Assembler().use(Picky, config={}).assemble()


async def test_component_without_name_is_rejected():
    class Nameless(Component):
        pass

    with pytest.raises(ConfigValidationError, match="name"):
        await Assembler().use(Nameless).assemble()


async def test_duplicate_component_name_is_rejected():
    class First(Component):
        name = "dup"
        provides = (P1,)

    class Second(Component):
        name = "dup"
        provides = (P2,)

    with pytest.raises(ConfigValidationError, match="dup"):
        await Assembler().use(First).use(Second).assemble()


async def test_setup_failure_rolls_back_earlier_components():
    cleaned: list[str] = []

    class Good(Component):
        name = "good"
        provides = (P1,)

        def setup(self) -> Disposable | None:
            async def cleanup() -> None:
                cleaned.append("good")

            return cleanup

    class Broken(Component):
        name = "broken"
        requires = (P1,)

        def setup(self) -> Disposable | None:
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await Assembler().use(Good).use(Broken).assemble()
    assert cleaned == ["good"]


async def test_shutdown_unwinds_lifo_and_is_repeatable():
    log: list[str] = []

    class First(Component):
        name = "first"
        provides = (P1,)

        def setup(self) -> Disposable | None:
            async def cleanup() -> None:
                log.append("first")

            return cleanup

    class Second(Component):
        name = "second"
        requires = (P1,)

        def setup(self) -> Disposable | None:
            async def cleanup() -> None:
                log.append("second")

            return cleanup

    tut = await Assembler().use(First).use(Second).assemble()
    await tut.shutdown()
    assert log == ["second", "first"]
    await tut.shutdown()
    assert log == ["second", "first"]


async def test_get_unknown_port_raises():
    tut = await Assembler().use(BusProvider).assemble()
    with pytest.raises(MissingPortError, match="P2"):
        tut.get(P2)
    await tut.shutdown()
