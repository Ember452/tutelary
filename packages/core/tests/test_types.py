"""types.py 的行为基线：frozen 不可变、Decision 三态、默认值与计量。"""

import dataclasses

import pytest

from tutelary.core.types import (
    Allow,
    Decision,
    Deny,
    ExecResult,
    ExecSpec,
    MemoryHit,
    Message,
    Suspend,
    TextBlock,
    ToolCall,
    ToolResult,
    ToolSpec,
    Usage,
)


def test_message_is_frozen():
    message = Message(role="user", content=(TextBlock(text="hi"),))
    with pytest.raises(dataclasses.FrozenInstanceError):
        message.role = "assistant"  # type: ignore[misc]


def test_tool_call_arguments_default_to_empty_mapping():
    call = ToolCall(id="c1", name="echo")
    assert dict(call.arguments) == {}


def test_tool_spec_parameters_default_to_empty_mapping():
    spec = ToolSpec(name="echo")
    assert dict(spec.parameters) == {}


def test_tool_result_defaults_to_success():
    result = ToolResult(call_id="c1", output="done")
    assert result.is_error is False


def test_usage_totals():
    usage = Usage(input_tokens=2, output_tokens=3)
    assert usage.total_tokens == 5


def test_decision_covers_three_states():
    allow = Allow()
    deny = Deny(reason="no")
    suspend = Suspend(prompt="ok?")
    decisions: list[Decision] = [allow, deny, suspend]
    assert isinstance(decisions[0], Allow)
    assert deny.reason == "no"
    assert suspend.prompt == "ok?"


def test_exec_spec_defaults_to_offline_and_no_timeout():
    spec = ExecSpec(command=("echo", "hi"))
    assert spec.network is False
    assert spec.timeout_seconds is None


def test_exec_result_defaults():
    result = ExecResult(exit_code=0)
    assert result.stdout == ""
    assert result.stderr == ""
    assert result.timed_out is False


def test_memory_hit_score_defaults_to_zero():
    hit = MemoryHit(id="m1", text="t")
    assert hit.score == 0.0
