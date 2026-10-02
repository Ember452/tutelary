"""token 计数：协议 + 确定性启发式实现。"""

from __future__ import annotations

import math
import unicodedata
from collections.abc import Sequence
from typing import Protocol

from tutelary.core.types import (
    Message,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
)

_MESSAGE_OVERHEAD_TOKENS = 4
"""每条消息的角色与框架开销，保守常数——启发式的一部分，不是精确值。"""


class TokenCounter(Protocol):
    """token 计数协议：注入真实计数器（如 tiktoken 封装）即可替换启发式。"""

    def count_text(self, text: str) -> int: ...

    def count_message(self, message: Message) -> int: ...


class HeuristicTokenCounter:
    """确定性启发式：CJK/全角字符 ≈ 1 token/字，其余 ≈ 1 token / 4 字符。

    为什么不内置 tiktoken：BPE 词表要联网下载，违背 only-* 的离线承诺；
    这里只承诺"确定性 + 量级正确"，精确计量由使用方注入自己的实现。
    """

    def count_text(self, text: str) -> int:
        wide = sum(1 for ch in text if unicodedata.east_asian_width(ch) in ("W", "F"))
        narrow = len(text) - wide
        return wide + math.ceil(narrow / 4)

    def count_message(self, message: Message) -> int:
        total = _MESSAGE_OVERHEAD_TOKENS
        for block in message.content:
            match block:
                case TextBlock(text=text) | ThinkingBlock(text=text):
                    total += self.count_text(text)
                case ToolResultBlock(result=result):
                    total += self.count_text(result.output)
                case ToolUseBlock(call=call):
                    total += self.count_text(call.name)
                    total += self.count_text(str(dict(call.arguments)))
        return total


def count_messages(counter: TokenCounter, messages: Sequence[Message]) -> int:
    """一段消息序列的合计 tokens。"""
    return sum(counter.count_message(message) for message in messages)
