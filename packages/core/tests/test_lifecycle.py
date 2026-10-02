"""lifecycle.py：effect 栈的 LIFO 语义、多形态清理与失败聚合。"""

import pytest

from tutelary.core.lifecycle import Component, EffectStack, SupportsAclose


class Probe:
    """记录调用顺序的同步清理函数。"""

    def __init__(self, log: list[str], name: str) -> None:
        self.log = log
        self.name = name

    def __call__(self) -> None:
        self.log.append(self.name)


def test_push_none_is_noop():
    stack = EffectStack()
    stack.push(None)
    assert stack.items == []


async def test_unwind_runs_lifo():
    log: list[str] = []
    stack = EffectStack()
    stack.push(Probe(log, "first"))
    stack.push(Probe(log, "second"))
    await stack.unwind()
    assert log == ["second", "first"]


async def test_unwind_supports_sync_async_and_aclose():
    log: list[str] = []

    class WithAclose:
        async def aclose(self) -> None:
            log.append("aclose")

    async def async_cleanup() -> None:
        log.append("async")

    stack = EffectStack()
    stack.push(Probe(log, "sync"))
    stack.push(async_cleanup)
    stack.push(WithAclose())
    await stack.unwind()
    assert log == ["aclose", "async", "sync"]


async def test_unwind_aggregates_failures_but_keeps_going():
    log: list[str] = []

    def boom() -> None:
        raise ValueError("boom")

    stack = EffectStack()
    stack.push(boom)
    stack.push(Probe(log, "ok"))
    stack.push(boom)
    with pytest.raises(ExceptionGroup) as info:
        await stack.unwind()
    assert log == ["ok"]
    assert len(info.value.exceptions) == 2


async def test_unwind_on_empty_stack_is_noop():
    await EffectStack().unwind()


def test_component_default_setup_returns_none():
    class Bare(Component):
        name = "bare"

    assert Bare().setup() is None


def test_supports_aclose_is_runtime_checkable():
    class Closable:
        async def aclose(self) -> None: ...

    assert isinstance(Closable(), SupportsAclose)
