"""Tutelary 记忆组件：Markdown 后端的 Memory 端口实现，写路径走事件。

只依赖 core；向量检索刻意不做——那是给第三方 Memory2 留的位置
（docs/09 M2 明确不做）。组件按子模块 import，本命名空间的重导出仅为
使用便利。
"""

from tutelary.memory.errors import MarkdownMemoryError, MemoryError
from tutelary.memory.provider import (
    DEFAULT_ROOT,
    MarkdownMemoryConfig,
    MarkdownProvider,
)
from tutelary.memory.store import SHARED_AGENT, MemoryEntry

__all__ = [
    "DEFAULT_ROOT",
    "SHARED_AGENT",
    "MarkdownMemoryConfig",
    "MarkdownMemoryError",
    "MarkdownProvider",
    "MemoryEntry",
    "MemoryError",
]
