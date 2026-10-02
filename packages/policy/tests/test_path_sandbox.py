"""path_sandbox.py：根内放行、逃逸拒绝、无路径参数不受影响。"""

from tutelary.core.types import Allow, Deny, ToolCall
from tutelary.policy.path_sandbox import PathSandbox

_ROOT = "./workspace"
_CALL_ID = "c1"


def _call(name: str, **arguments: str) -> ToolCall:
    return ToolCall(id=_CALL_ID, name=name, arguments=arguments)


def test_path_under_root_is_allowed():
    policy = PathSandbox((_ROOT,))
    decision = policy.check(_call("read_file", path="./workspace/notes/a.md"))
    assert decision == Allow()


def test_absolute_path_outside_root_is_denied():
    policy = PathSandbox((_ROOT,))
    decision = policy.check(_call("read_file", path="C:/Windows/system32/config"))
    assert isinstance(decision, Deny)
    assert "逃逸" in decision.reason


def test_dotdot_escape_is_denied():
    policy = PathSandbox((_ROOT,))
    decision = policy.check(_call("read_file", path="./workspace/../../etc/passwd"))
    assert isinstance(decision, Deny)


def test_call_without_path_arguments_is_unaffected():
    policy = PathSandbox((_ROOT,))
    assert policy.check(_call("web_search", query="tutelary")) == Allow()


def test_custom_argument_keys():
    policy = PathSandbox((_ROOT,), argument_keys=("target",))
    assert policy.check(_call("write", target="./workspace/out.md")) == Allow()
    assert isinstance(policy.check(_call("write", path="./etc/passwd")), Allow)


def test_check_is_repeatable():
    policy = PathSandbox((_ROOT,))
    call = _call("read_file", path="./workspace/a.md")
    assert policy.check(call) == policy.check(call)
