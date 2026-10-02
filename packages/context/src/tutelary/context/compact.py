"""压缩：唯一的 M1 策略——最老优先折叠成摘要（docs/09 M1：一个压缩策略）。

两个承诺：
1. 摘要经 Provider 端口产生——内核"端口可消费性"假设的第一次真实检验；
2. ``keep_substrings`` 命中的消息钉住不折叠——"must-survive 全保留"是
   机器可判承诺；钉住部分本身就超预算、或压缩到头仍超预算时抛
   ContextBudgetError，不静默丢弃。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from tutelary.context.counter import HeuristicTokenCounter, TokenCounter, count_messages
from tutelary.context.errors import ContextBudgetError
from tutelary.core.events import StreamText
from tutelary.core.ports import Provider
from tutelary.core.types import LLMRequest, Message, TextBlock, ThinkingBlock, ToolResultBlock

_SUMMARY_RESERVE_TOKENS = 64
"""摘要的预估开销：真实值出来后按实测记账，估小了循环会再折叠一轮。"""

_COMPACT_MODEL = "tutelary-compact"
"""摘要请求的模型名——脚本化 fake 只认轮次不认模型，真实接入由使用方映射。"""


def message_text(message: Message) -> str:
    """拼接一条消息里的全部文本（keep_substrings 的匹配面）。"""
    parts: list[str] = []
    for block in message.content:
        if isinstance(block, TextBlock | ThinkingBlock):
            parts.append(block.text)
        elif isinstance(block, ToolResultBlock):
            parts.append(block.result.output)
    return "\n".join(parts)


@dataclass(frozen=True, slots=True)
class CompactionStats:
    """一次折叠的账目（进内省报告与 CompactNotification）。"""

    tokens_before: int
    tokens_after: int
    folded_messages: int
    summary: str


class SummarizeFoldStrategy:
    """最老优先折叠：超出目标的部分折成一段摘要，置于历史最前。

    正确性优先于调用数：摘要实际大小只有生成后才知道，估小了就再把
    最老的保留消息挪进折叠桶重新生成——最坏情况多轮 Provider 调用。
    """

    def __init__(self, provider: Provider, counter: TokenCounter | None = None) -> None:
        self._provider = provider
        self._counter = counter if counter is not None else HeuristicTokenCounter()

    async def compact(
        self,
        history: Sequence[Message],
        *,
        target_tokens: int,
        keep_substrings: Sequence[str] = (),
    ) -> tuple[list[Message], CompactionStats]:
        """把 history 压到 target_tokens 以内；返回（新历史，账目）。

        受保护（命中 keep 子串）的消息原样保留、位置不变；其余最老优先
        进入折叠桶，折叠桶以摘要消息顶替。
        """
        tokens_before = count_messages(self._counter, history)
        if tokens_before <= target_tokens:
            return list(history), CompactionStats(
                tokens_before=tokens_before,
                tokens_after=tokens_before,
                folded_messages=0,
                summary="",
            )
        pinned = [m for m in history if any(s in message_text(m) for s in keep_substrings)]
        pinned_ids = {id(m) for m in pinned}
        droppable = [m for m in history if id(m) not in pinned_ids]

        pinned_tokens = count_messages(self._counter, pinned)
        if pinned_tokens + _SUMMARY_RESERVE_TOKENS > target_tokens:
            raise ContextBudgetError(
                f"受保护内容 {pinned_tokens} tokens 加摘要开销已超过历史预算 "
                f"{target_tokens}，无法在不丢弃受保护内容的情况下完成压缩"
            )

        keep_count = 0  # 从 droppable 尾部（最新侧）保留的消息数
        while True:
            fold_bucket = droppable[: len(droppable) - keep_count]
            summary = await self._summarize(fold_bucket) if fold_bucket else ""
            folded_ids = {id(m) for m in fold_bucket}
            result = [m for m in history if id(m) not in folded_ids]
            if fold_bucket:
                summary_message = Message(
                    role="user", content=(TextBlock(text=f"[历史摘要] {summary}"),)
                )
                result.insert(0, summary_message)
            tokens_after = count_messages(self._counter, result)
            if tokens_after <= target_tokens:
                stats = CompactionStats(
                    tokens_before=tokens_before,
                    tokens_after=tokens_after,
                    folded_messages=len(fold_bucket),
                    summary=summary,
                )
                return result, stats
            if keep_count >= len(droppable):
                raise ContextBudgetError(
                    f"全部可折叠内容都已折叠，实测 {tokens_after} tokens 仍超预算 {target_tokens}"
                )
            keep_count += 1

    async def _summarize(self, fold_bucket: Sequence[Message]) -> str:
        folded_text = "\n\n".join(f"[{m.role}] {message_text(m)}" for m in fold_bucket)
        request = LLMRequest(
            model=_COMPACT_MODEL,
            messages=(
                Message(
                    role="user",
                    content=(
                        TextBlock(
                            text="把下面的对话历史折叠成一份摘要，"
                            "保留全部事实、决定与未完成事项：\n\n" + folded_text
                        ),
                    ),
                ),
            ),
        )
        chunks: list[str] = []
        async for event in self._provider.stream(request):
            if isinstance(event, StreamText):
                chunks.append(event.delta)
        return "".join(chunks).strip()
