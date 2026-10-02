"""ContextGovernor：每次 LLM 调用前执行预算约束，全程记账（docs/09 M1）。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from tutelary.context.budget import Budget, BudgetConfig
from tutelary.context.compact import CompactionStats, SummarizeFoldStrategy
from tutelary.context.counter import HeuristicTokenCounter, TokenCounter, count_messages
from tutelary.context.offload import OffloadStore
from tutelary.context.report import IntrospectionReport, OffloadRecord
from tutelary.core.events import Bus, CompactNotification, CompactStarted, UsageEvent
from tutelary.core.lifecycle import Component, Disposable
from tutelary.core.ports import Provider
from tutelary.core.types import Message, ToolResult, ToolResultBlock

OFFLOAD_THRESHOLD_TOKENS = 2000
"""工具结果卸载阈值：超过即移出上下文。M1 固定常量，随评测集调参再配置化。"""


@dataclass(frozen=True, slots=True)
class EnforcementResult:
    """一次 enforce 的产出：约束后的消息序列 + 动作账目。"""

    messages: list[Message]
    compacted: bool
    offloaded: int


class Governor(Protocol):
    """上下文治理端口的 M1 工作草案。

    M3 引擎消费时按 04 §5 演进规则升格进 core——现在放 context 包，
    是因为还没有第二个消费者，先进 core 属于过度设计。
    """

    offload_store: OffloadStore

    async def enforce(
        self, messages: Sequence[Message], *, keep_substrings: Sequence[str] = ()
    ) -> EnforcementResult: ...

    def report(self) -> IntrospectionReport: ...


class ContextGovernor(Component):
    """旗舰组件：上下文治理器。

    requires Provider（摘要生成）+ Bus（压缩事件广播、用量计量）。
    组件契约：预算内不改写内容；超预算时兑现两条硬指标——
    history ≤ 预算、keep_substrings 全保留——做不到就抛类型化错误。
    """

    name = "context"
    provides = (Governor,)
    requires = (Provider, Bus)
    config_model = BudgetConfig

    def __init__(self, provider: Provider, bus: Bus, config: Budget | None = None) -> None:
        self._provider = provider
        self._bus = bus
        self._budget = config if config is not None else Budget()
        self._counter: TokenCounter = HeuristicTokenCounter()
        self._strategy = SummarizeFoldStrategy(provider, self._counter)
        self.offload_store = OffloadStore()
        self._measured: dict[str, int] = {}
        self._usage_input = 0
        self._usage_output = 0
        self._compactions: list[CompactionStats] = []
        self._offloads: list[OffloadRecord] = []

    def setup(self) -> Disposable | None:
        """订阅 UsageEvent 计量；Disposable 进 effect 栈，shutdown 自动退订。"""

        async def on_usage(event: UsageEvent) -> None:
            self._usage_input += event.usage.input_tokens
            self._usage_output += event.usage.output_tokens

        return self._bus.observe(UsageEvent, on_usage)

    async def enforce(
        self, messages: Sequence[Message], *, keep_substrings: Sequence[str] = ()
    ) -> EnforcementResult:
        """按预算约束消息序列：卸载超大工具结果 →（需要时）压缩 → 记账。"""
        system = [m for m in messages if m.role == "system"]
        history = [m for m in messages if m.role != "system"]

        slimmed: list[Message] = []
        offload_records: list[OffloadRecord] = []
        for message in history:
            replaced, records = self._offload_large_results(message)
            slimmed.append(replaced)
            offload_records.extend(records)
        self._offloads.extend(offload_records)

        history_budget = self._budget.section_tokens("history")
        compacted = False
        if count_messages(self._counter, slimmed) > history_budget:
            slimmed, stats = await self._strategy.compact(
                slimmed, target_tokens=history_budget, keep_substrings=keep_substrings
            )
            compacted = True
            self._compactions.append(stats)
            await self._bus.emit(CompactStarted(reason="budget", tokens_before=stats.tokens_before))
            await self._bus.emit(
                CompactNotification(summary=stats.summary, tokens_after=stats.tokens_after)
            )

        self._measured = {
            "system": count_messages(self._counter, system),
            "history": count_messages(self._counter, slimmed),
        }
        return EnforcementResult(
            messages=[*system, *slimmed],
            compacted=compacted,
            offloaded=len(offload_records),
        )

    def report(self) -> IntrospectionReport:
        """当前内省快照。"""
        return IntrospectionReport(
            budget=self._budget,
            measured=dict(self._measured),
            usage_input=self._usage_input,
            usage_output=self._usage_output,
            compactions=tuple(self._compactions),
            offloads=tuple(self._offloads),
        )

    def _offload_large_results(self, message: Message) -> tuple[Message, list[OffloadRecord]]:
        """把超大工具结果换成占位符，原文进卸载仓库；无超限则原样返回。"""
        records: list[OffloadRecord] = []
        content = list(message.content)
        for index, block in enumerate(content):
            if not isinstance(block, ToolResultBlock):
                continue
            tokens = self._counter.count_text(block.result.output)
            if tokens <= OFFLOAD_THRESHOLD_TOKENS:
                continue
            self.offload_store.put(block.result.call_id, block.result.output)
            content[index] = ToolResultBlock(
                result=ToolResult(
                    call_id=block.result.call_id,
                    is_error=block.result.is_error,
                    output=(
                        f"[工具结果已卸载：{tokens} tokens，"
                        f"用 OffloadStore.get({block.result.call_id!r}) 取回]"
                    ),
                )
            )
            records.append(OffloadRecord(call_id=block.result.call_id, tokens=tokens))
        if not records:
            return message, []
        return Message(role=message.role, content=tuple(content)), records
