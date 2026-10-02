"""Tutelary 旗舰：上下文治理——预算声明、压缩、卸载、token 内省（docs/01 §3）。

只依赖 core；公开 API 按子模块 import，本命名空间的重导出仅为使用便利。
"""

from tutelary.context.budget import SECTIONS, Budget, BudgetConfig
from tutelary.context.compact import CompactionStats, SummarizeFoldStrategy, message_text
from tutelary.context.counter import HeuristicTokenCounter, TokenCounter, count_messages
from tutelary.context.errors import ContextBudgetError, ContextError, OffloadMissError
from tutelary.context.governor import (
    OFFLOAD_THRESHOLD_TOKENS,
    ContextGovernor,
    EnforcementResult,
    Governor,
)
from tutelary.context.offload import OffloadStore
from tutelary.context.report import IntrospectionReport, OffloadRecord

__all__ = [
    "OFFLOAD_THRESHOLD_TOKENS",
    "SECTIONS",
    "Budget",
    "BudgetConfig",
    "CompactionStats",
    "ContextBudgetError",
    "ContextError",
    "ContextGovernor",
    "EnforcementResult",
    "Governor",
    "HeuristicTokenCounter",
    "IntrospectionReport",
    "OffloadMissError",
    "OffloadRecord",
    "OffloadStore",
    "SummarizeFoldStrategy",
    "TokenCounter",
    "count_messages",
    "message_text",
]
