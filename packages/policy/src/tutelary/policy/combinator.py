"""组合子：把多个 Policy 组合成一个（docs/07 M2 的"可组合策略"）。

合并语义是确定性的（docs/04 §2 的 Decision 三态）：

- ``AllOf``：任一 Deny 即 Deny（第一条为准）；否则任一 Suspend 即
  Suspend；否则 Allow。
- ``AnyOf``：任一 Allow 即 Allow；否则任一 Suspend 即 Suspend；否则
  Deny。

policy 包交付**纯对象**而非 Component：组合子需要拿子策略实例，而
装配器的端口是单提供者语义，装不下"多个 Policy 组合"——装配面留给
M3 引擎落地时的 ADR（docs/plans/2026-10-02-m2-tasks.md §2）。
"""

from __future__ import annotations

from tutelary.core.ports import Policy
from tutelary.core.types import Allow, Decision, Deny, Suspend, ToolCall


class AllOf:
    """全部子判定都放行才放行。"""

    def __init__(self, *policies: Policy) -> None:
        self._policies = policies

    def check(self, call: ToolCall) -> Decision:
        decisions = [policy.check(call) for policy in self._policies]
        for decision in decisions:
            if isinstance(decision, Deny):
                return decision
        for decision in decisions:
            if isinstance(decision, Suspend):
                return decision
        return Allow()


class AnyOf:
    """任一子判定放行即放行。"""

    def __init__(self, *policies: Policy) -> None:
        self._policies = policies

    def check(self, call: ToolCall) -> Decision:
        decisions = [policy.check(call) for policy in self._policies]
        for decision in decisions:
            if isinstance(decision, Allow):
                return decision
        for decision in decisions:
            if isinstance(decision, Suspend):
                return decision
        return Deny(reason="所有子策略均未放行")
