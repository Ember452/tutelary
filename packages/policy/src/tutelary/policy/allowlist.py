"""Allowlist：名单制策略——名单外的工具一律 Deny。"""

from __future__ import annotations

from tutelary.core.types import Allow, Decision, Deny, ToolCall


class Allowlist:
    """只放行显式列出的工具名；check 无副作用（docs/04 §2）。"""

    def __init__(self, allowed: tuple[str, ...]) -> None:
        self._allowed = frozenset(allowed)

    def check(self, call: ToolCall) -> Decision:
        if call.name in self._allowed:
            return Allow()
        return Deny(reason=f"工具 {call.name!r} 不在放行名单中")
