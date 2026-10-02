"""memory 的契约套件：任何 Memory 实现都要过的检查（docs/04 §4）。

与 context 套件同构：只 import core，用 core 装配器与 fakes 驱动工厂
给出的**任意**实现。工厂契约：``--tutelary-factory`` 指向被测组件类；
实现必须可无配置装配（内置默认即可用），并暴露 ``seed(scope, text)
-> str`` 作为播种测试面（端口本身没有写方法——写路径走事件）。

检查 6（docs/04 §4 的"错误路径抛类型化错误"）对 memory 不适用：它的
契约本身就是"无命中不抛错"，不为凑数发明错误场景。
"""

from __future__ import annotations

import asyncio
from typing import Any

from tutelary.core import (
    Assembler,
    Bus,
    FakeBus,
    TurnCommitted,
)
from tutelary.core.types import MemoryScope

_SCOPE = MemoryScope(agent_id="suite-agent", session_id="s1")


class _BusHolder(FakeBus):
    name = "bus"
    provides = (Bus,)


def run_checks(component_class: type[Any]) -> list[tuple[str, bool, str]]:
    """套件入口（ContractItem 调用）：逐项检查，返回（名称，是否通过，说明）。"""
    return asyncio.run(_run_checks(component_class))


async def _run_checks(component_class: type[Any]) -> list[tuple[str, bool, str]]:
    checks: list[tuple[str, bool, str]] = []

    async def check(name: str, body: Any) -> None:
        try:
            await body()
            checks.append((name, True, "通过"))
        except AssertionError as exc:
            checks.append((name, False, str(exc) or "断言失败"))
        except AttributeError as exc:
            checks.append((name, False, f"实现缺少契约要求的测试面：{exc}"))

    async def scenario() -> Any:
        tut = await Assembler().use(_BusHolder).use(component_class).assemble()
        return tut, tut.get(component_class.provides[0])

    async def check_seed_surface_exists() -> None:
        tut, memory = await scenario()
        assert hasattr(memory, "seed"), "实现必须暴露 seed(scope, text) -> str 契约测试面"
        await tut.shutdown()

    async def check_seed_recall_hit() -> None:
        tut, memory = await scenario()
        memory.seed(_SCOPE, "契约种子内容")
        hits = await memory.recall("种子", _SCOPE)
        assert hits, "种子后同 scope recall 未命中"
        assert any("契约种子内容" in hit.text for hit in hits)
        await tut.shutdown()

    async def check_load_context_contains_seed() -> None:
        tut, memory = await scenario()
        memory.seed(_SCOPE, "契约种子内容")
        context = await memory.load_context("种子", _SCOPE)
        assert "契约种子内容" in context, "load_context 未包含种子内容"
        await tut.shutdown()

    async def check_turn_committed_write_is_idempotent() -> None:
        tut, memory = await scenario()
        bus = tut.get(Bus)
        event = TurnCommitted(turn_id="contract-t1", text="事件写入的记忆", session_id="s1")
        await bus.emit(event)
        await bus.emit(event)
        hits = await memory.recall("事件写入", _SCOPE)
        assert len(hits) == 1, f"重复派发 TurnCommitted 未幂等：得到 {len(hits)} 条"
        await tut.shutdown()

    async def check_recall_no_hit_returns_empty() -> None:
        tut, memory = await scenario()
        memory.seed(_SCOPE, "别的内容")
        assert await memory.recall("绝对不存在的内容", _SCOPE) == [], "无命中应返回空列表"
        await tut.shutdown()

    async def check_shutdown_is_repeatable() -> None:
        tut, _memory = await scenario()
        await tut.shutdown()
        await tut.shutdown()

    for name, body in (
        ("seed 测试面就绪", check_seed_surface_exists),
        ("种子后 recall 命中", check_seed_recall_hit),
        ("load_context 含种子内容", check_load_context_contains_seed),
        ("TurnCommitted 落库且幂等", check_turn_committed_write_is_idempotent),
        ("无命中返回空列表不抛错", check_recall_no_hit_returns_empty),
        ("shutdown 幂等", check_shutdown_is_repeatable),
    ):
        await check(name, body)

    return checks
