"""context 的契约套件：任何 Governor 实现都要过的检查（docs/04 §4）。

经入口点组 ``tutelary.contract_suites`` 注册为 "context"。本模块刻意只
import core——用 core 装配器 + core fakes 驱动工厂给出的**任意**实现，
被检对象与检查器之间零横向依赖，中立性由结构保证。

检查即 docs/09 M1 两条硬指标的机器化 + 卸载往返 + 报告完备 + 类型化错误。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from tutelary.core import (
    Assembler,
    Bus,
    FakeBus,
    FakeProvider,
    LLMEvent,
    Message,
    Provider,
    StreamText,
    TextBlock,
    ToolResult,
    ToolResultBlock,
    TutelaryError,
    Usage,
    UsageEvent,
)
from tutelary.core.types import LLMRequest, ThinkingBlock

_MUST_SURVIVE = "回滚预案定在周五窗口执行"
_FILLER_TURNS = 40
_BIG_OUTPUT = "日志行 " * 3000
_BIG_CALL_ID = "call-logs"


class _ScriptedProvider:
    """脚本化 Provider 组件：摘要轮固定回一段确定性文本。"""

    name = "provider"
    provides = (Provider,)

    def __init__(self) -> None:
        summary_turn = [
            StreamText(delta="摘要：早期讨论覆盖部署窗口与回滚预案。"),
            UsageEvent(usage=Usage(input_tokens=500, output_tokens=30)),
        ]
        self._fake = FakeProvider(*([summary_turn] * 8))

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        async for event in self._fake.stream(request):
            yield event


class _BusHolder(FakeBus):
    name = "bus"
    provides = (Bus,)


def _flatten(message: Message) -> str:
    parts: list[str] = []
    for block in message.content:
        if isinstance(block, TextBlock | ThinkingBlock):
            parts.append(block.text)
        elif isinstance(block, ToolResultBlock):
            parts.append(block.result.output)
    return "\n".join(parts)


def _conversation() -> list[Message]:
    filler = [
        Message(
            role="user" if i % 2 == 0 else "assistant",
            content=(TextBlock(text=f"轮次 {i}：{'细节。' * 150}"),),
        )
        for i in range(_FILLER_TURNS)
    ]
    tool_turn = Message(
        role="assistant",
        content=(ToolResultBlock(result=ToolResult(call_id=_BIG_CALL_ID, output=_BIG_OUTPUT)),),
    )
    return [
        Message(role="system", content=(TextBlock(text="你是部署助手。"),)),
        Message(role="user", content=(TextBlock(text=f"早会记录：{_MUST_SURVIVE}"),)),
        *filler,
        tool_turn,
    ]


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
        except TutelaryError as exc:
            checks.append((name, False, f"抛出类型化错误：{exc}"))

    async def scenario() -> Any:
        tut = (
            await Assembler().use(_ScriptedProvider).use(_BusHolder).use(component_class).assemble()
        )
        return tut, tut.get(component_class.provides[0])

    async def check_budget_adherence() -> None:
        tut, governor = await scenario()
        result = await governor.enforce(_conversation(), keep_substrings=[_MUST_SURVIVE])
        report = governor.report()
        history_quota = report.budget.section_tokens("history")
        assert result.compacted, "超预算会话应触发压缩"
        assert report.measured["history"] <= history_quota, (
            f"硬指标①：压缩后 history {report.measured['history']} 超预算 {history_quota}"
        )
        await tut.shutdown()

    async def check_must_survive_retention() -> None:
        tut, governor = await scenario()
        result = await governor.enforce(_conversation(), keep_substrings=[_MUST_SURVIVE])
        flat = "\n".join(_flatten(m) for m in result.messages)
        assert _MUST_SURVIVE in flat, "硬指标②：must-survive 内容在压缩输出中丢失"
        await tut.shutdown()

    async def check_offload_roundtrip() -> None:
        tut, governor = await scenario()
        result = await governor.enforce(_conversation())
        flat = "\n".join(_flatten(m) for m in result.messages)
        assert _BIG_OUTPUT not in flat, "超大工具结果未被卸载"
        assert governor.offload_store.get(_BIG_CALL_ID) == _BIG_OUTPUT, "卸载内容无法按引用取回"
        await tut.shutdown()

    async def check_report_completeness() -> None:
        tut, governor = await scenario()
        bus = tut.get(Bus)
        await bus.emit(UsageEvent(usage=Usage(input_tokens=7, output_tokens=3)))
        await governor.enforce(_conversation(), keep_substrings=[_MUST_SURVIVE])
        report = governor.report()
        assert report.measured.get("history") is not None, "报告缺 history 实测"
        assert report.measured.get("system") is not None, "报告缺 system 实测"
        assert report.usage_input == 7 and report.usage_output == 3, "UsageEvent 未被计量"
        assert len(report.compactions) >= 1, "压缩没有进报告"
        rendered = report.render()
        assert rendered and "token 内省" in rendered, "报告渲染为空"
        await tut.shutdown()

    async def check_typed_error_on_impossible_budget() -> None:
        tut, governor = await scenario()
        try:
            # 全部填充轮都命中 → 受保护内容远超预算，必须抛类型化错误而非静默
            await governor.enforce(_conversation(), keep_substrings=["轮次", _MUST_SURVIVE])
        except TutelaryError:
            pass
        else:
            raise AssertionError("不可能满足的预算未抛 TutelaryError 子类")
        finally:
            await tut.shutdown()

    for name, body in (
        ("预算达标（硬指标①）", check_budget_adherence),
        ("must-survive 全保留（硬指标②）", check_must_survive_retention),
        ("卸载往返", check_offload_roundtrip),
        ("内省报告完备", check_report_completeness),
        ("不可能预算抛类型化错误", check_typed_error_on_impossible_budget),
    ):
        await check(name, body)

    return checks
