"""context 的类型化错误（挂在 core 的 TutelaryError 体系之下，AGENTS §4.5）。"""

from tutelary.core.errors import TutelaryError


class ContextError(TutelaryError):
    """context 组件错误的基类。"""


class ContextBudgetError(ContextError):
    """预算无法满足：受保护内容本身就超预算，或压缩到头仍超预算。

    fail fast——不静默丢弃受保护内容，也不交付超预算的上下文。
    """


class OffloadMissError(ContextError):
    """按引用取回卸载内容时未命中。"""
