"""counter.py：启发式的确定性与量级合理、消息合计。"""

from tutelary.context.counter import HeuristicTokenCounter, count_messages
from tutelary.core.types import Message, TextBlock, ToolResult, ToolResultBlock


def test_cjk_counts_about_one_token_per_char():
    counter = HeuristicTokenCounter()
    assert counter.count_text("部署窗口") == 4


def test_ascii_counts_about_one_token_per_four_chars():
    counter = HeuristicTokenCounter()
    assert counter.count_text("abcdefgh") == 2


def test_mixed_text_is_deterministic():
    counter = HeuristicTokenCounter()
    text = "预算 8000 tokens，包含 padding。"
    assert counter.count_text(text) == counter.count_text(text)


def test_message_counts_blocks_plus_overhead():
    counter = HeuristicTokenCounter()
    message = Message(
        role="assistant",
        content=(
            TextBlock(text="abcdefgh"),
            ToolResultBlock(result=ToolResult(call_id="c", output="部署窗口")),
        ),
    )
    # 8 ascii → 2 tokens，4 cjk → 4 tokens，再加每条消息固定开销 4
    assert counter.count_message(message) == 10


def test_count_messages_sums():
    counter = HeuristicTokenCounter()
    messages = [Message(role="user", content=(TextBlock(text="abcdefgh"),))] * 3
    assert count_messages(counter, messages) == 3 * counter.count_message(messages[0])
