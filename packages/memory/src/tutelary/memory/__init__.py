"""Tutelary 记忆组件：Markdown 后端的 Memory 端口实现，写路径走事件。

只依赖 core；向量检索刻意不做——那是给第三方 Memory2 留的位置
（docs/09 M2 明确不做）。
"""

from tutelary.memory.errors import MarkdownMemoryError, MemoryError

__all__ = ["MarkdownMemoryError", "MemoryError"]
