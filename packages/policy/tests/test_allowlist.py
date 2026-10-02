"""allowlist.py：名单命中放行、未命中拒绝、check 可重复调用。"""

from tutelary.core.types import Allow, Deny, ToolCall
from tutelary.policy.allowlist import Allowlist

_CALL = ToolCall(id="c1", name="read_file")


def test_listed_tool_is_allowed():
    assert Allowlist(("read_file",)).check(_CALL) == Allow()


def test_unlisted_tool_is_denied_with_reason():
    decision = Allowlist(("run_cmd",)).check(_CALL)
    assert decision == Deny(reason="工具 'read_file' 不在放行名单中")


def test_check_is_repeatable():
    policy = Allowlist(("read_file",))
    assert policy.check(_CALL) == policy.check(_CALL)
