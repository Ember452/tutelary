"""Tutelary 权限组件：可组合策略 + Suspend 审批判定侧。

只依赖 core；policy 是纯对象而非 Component（决策与装配分离，装配面
留给 M3 的端口增补，见 docs/plans/2026-10-02-m2-tasks.md §2）。
"""

from tutelary.policy.allowlist import Allowlist
from tutelary.policy.approval import DEFAULT_PROMPT_TEMPLATE, ApprovalGate
from tutelary.policy.combinator import AllOf, AnyOf
from tutelary.policy.path_sandbox import DEFAULT_PATH_KEYS, PathSandbox

__all__ = [
    "DEFAULT_PATH_KEYS",
    "DEFAULT_PROMPT_TEMPLATE",
    "AllOf",
    "Allowlist",
    "AnyOf",
    "ApprovalGate",
    "PathSandbox",
]
