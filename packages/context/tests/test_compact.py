"""compact.py：折叠顺序、钉住承诺、预算不可能与摘要来源。"""

import pytest

from tutelary.context.compact import SummarizeFoldStrategy, message_text
from tutelary.context.errors import ContextBudgetError
from tutelary.core.events import StreamText, UsageEvent
from tutelary.core.fakes import FakeProvider
from tutelary.core.types import Message, TextBlock, ToolResult, ToolResultBlock, Usage


def _turn(text: str) -> Message:
    return Message(role="user", content=(TextBlock(text=text),))


def _provider() -> FakeProvider:
    summary_turn = [
        StreamText(delta="摘要：早期讨论已折叠。"),
        UsageEvent(usage=Usage(input_tokens=100, output_tokens=10)),
    ]
    return FakeProvider(*([summary_turn] * 6))


def _filler(count: int) -> list[Message]:
    return [_turn(f"old-{i}：{'细节。' * 60}") for i in range(count)]


def test_message_text_covers_blocks():
    message = Message(
        role="user",
        content=(
            TextBlock(text="甲"),
            ToolResultBlock(result=ToolResult(call_id="c", output="乙")),
        ),
    )
    assert "甲" in message_text(message)
    assert "乙" in message_text(message)


async def test_under_target_history_is_untouched():
    strategy = SummarizeFoldStrategy(_provider())
    history = [_turn("abcdefgh" * 10)]
    result, stats = await strategy.compact(history, target_tokens=1000)
    assert result == history
    assert stats.folded_messages == 0
    assert stats.tokens_after == stats.tokens_before


async def test_over_target_folds_oldest_and_summarizes():
    strategy = SummarizeFoldStrategy(_provider())
    history = _filler(10)
    result, stats = await strategy.compact(history, target_tokens=300)
    assert stats.folded_messages == 10
    assert stats.summary.startswith("摘要：")
    assert result[0].content[0].text.startswith("[历史摘要]")  # type: ignore[union-attr]
    assert stats.tokens_after <= 300
    assert history[0] not in result


async def test_keep_substrings_are_pinned():
    strategy = SummarizeFoldStrategy(_provider())
    pinned = _turn("必须保留：回滚预案定在周五")
    history = [pinned, *_filler(10)]
    result, _ = await strategy.compact(
        history, target_tokens=300, keep_substrings=["回滚预案定在周五"]
    )
    assert pinned in result
    assert result[0].content[0].text.startswith("[历史摘要]")  # type: ignore[union-attr]


async def test_pinned_over_budget_raises():
    strategy = SummarizeFoldStrategy(_provider())
    huge_pinned = _turn("受保护。" * 2000)
    with pytest.raises(ContextBudgetError, match="受保护内容"):
        await strategy.compact([huge_pinned], target_tokens=300, keep_substrings=["受保护"])


async def test_unreachable_target_raises_even_after_folding_all():
    huge_summary = [StreamText(delta="巨摘要" * 10000)]
    strategy = SummarizeFoldStrategy(FakeProvider(*([huge_summary] * 6)))
    with pytest.raises(ContextBudgetError, match="仍超预算"):
        await strategy.compact(_filler(3), target_tokens=100)
