"""approval.py：命中挂起、未命中放行、prompt 可展示且可定制。"""

from tutelary.core.types import Allow, Suspend, ToolCall
from tutelary.policy.approval import ApprovalGate

_CALL = ToolCall(id="c1", name="run_cmd")


def test_default_gate_suspends_every_tool():
    decision = ApprovalGate().check(_CALL)
    assert isinstance(decision, Suspend)
    assert "run_cmd" in decision.prompt


def test_gate_suspends_only_listed_tools():
    policy = ApprovalGate(tools=("run_cmd",))
    assert isinstance(policy.check(_CALL), Suspend)
    assert policy.check(ToolCall(id="c2", name="read_file")) == Allow()


def test_prompt_template_is_customizable():
    policy = ApprovalGate(prompt_template="确认执行 {tool}？[y/N]")
    assert policy.check(_CALL) == Suspend(prompt="确认执行 run_cmd？[y/N]")


def test_check_is_repeatable():
    policy = ApprovalGate()
    assert policy.check(_CALL) == policy.check(_CALL)
