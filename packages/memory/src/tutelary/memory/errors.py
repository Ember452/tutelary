"""memory 的类型化错误（挂在 core 的 TutelaryError 体系之下，AGENTS §4.5）。"""

from tutelary.core.errors import TutelaryError


class MemoryError(TutelaryError):
    """memory 组件错误的基类。"""


class MarkdownMemoryError(MemoryError):
    """Markdown 存储的配置或读写异常。"""
