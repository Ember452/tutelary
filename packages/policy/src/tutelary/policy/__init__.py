"""Tutelary 权限组件：可组合策略 + Suspend 审批判定侧。

只依赖 core；policy 是纯对象而非 Component（决策与装配分离，装配面
留给 M3 的端口增补，见 docs/plans/2026-10-02-m2-tasks.md §2）。
"""

from tutelary.policy.combinator import AllOf, AnyOf

__all__ = ["AllOf", "AnyOf"]
