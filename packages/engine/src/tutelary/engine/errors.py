"""engine 的类型化错误（挂在 core 的 TutelaryError 体系之下，AGENTS §4.5）。"""

from tutelary.core.errors import TutelaryError


class EngineError(TutelaryError):
    """engine 错误的基类。"""


class NoPendingTurnError(EngineError):
    """resume 时该会话没有挂起中的回合。"""


class ToolHopsExceededError(EngineError):
    """单回合工具调用轮数超过上限——通常是模型陷入工具循环。"""
