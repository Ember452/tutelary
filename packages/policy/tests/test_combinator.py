"""combinator.py：AllOf / AnyOf 的确定性合并语义。"""

from tutelary.core.types import Allow, Decision, Deny, Suspend, ToolCall
from tutelary.policy import AllOf, AnyOf

_CALL = ToolCall(id="c1", name="read_file")


class _AlwaysAllow:
    def check(self, call: ToolCall) -> Decision:
        return Allow()


class _AlwaysDeny:
    def check(self, call: ToolCall) -> Decision:
        return Deny(reason="拒绝")


class _AlwaysSuspend:
    def check(self, call: ToolCall) -> Decision:
        return Suspend(prompt="需要审批")


def test_allof_any_deny_wins_first():
    policy = AllOf(_AlwaysAllow(), _AlwaysDeny(), _AlwaysSuspend())
    assert policy.check(_CALL) == Deny(reason="拒绝")


def test_allof_suspend_when_no_deny():
    policy = AllOf(_AlwaysAllow(), _AlwaysSuspend())
    assert policy.check(_CALL) == Suspend(prompt="需要审批")


def test_allof_allow_when_all_allow():
    policy = AllOf(_AlwaysAllow(), _AlwaysAllow())
    assert policy.check(_CALL) == Allow()


def test_anyof_any_allow_wins():
    policy = AnyOf(_AlwaysDeny(), _AlwaysAllow(), _AlwaysSuspend())
    assert policy.check(_CALL) == Allow()


def test_anyof_suspend_when_no_allow():
    policy = AnyOf(_AlwaysDeny(), _AlwaysSuspend())
    assert policy.check(_CALL) == Suspend(prompt="需要审批")


def test_anyof_deny_when_all_deny():
    policy = AnyOf(_AlwaysDeny(), _AlwaysDeny())
    assert policy.check(_CALL) == Deny(reason="所有子策略均未放行")
