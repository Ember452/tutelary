"""events.py：事件词表的构造与 frozen 承诺（17 个基线事件）。"""

import dataclasses
from typing import Any

import pytest

from tutelary.core.events import (
    BudgetBreached,
    CompactNotification,
    CompactStarted,
    ErrorEvent,
    Event,
    HookEvent,
    LoopComplete,
    PermissionRequest,
    PermissionResponse,
    RetryEvent,
    StreamText,
    ThinkingText,
    ToolResultEvent,
    ToolUseEvent,
    TurnCommitted,
    TurnComplete,
    TurnStarted,
    UsageEvent,
)
from tutelary.core.types import Allow, ToolCall, ToolResult, Usage

CALL = ToolCall(id="c1", name="echo")
RESULT = ToolResult(call_id="c1", output="ok")
USAGE = Usage(input_tokens=1, output_tokens=1)

SAMPLES: tuple[tuple[type[Event], dict[str, Any]], ...] = (
    (TurnStarted, {"session_id": "s", "input": "hi"}),
    (ThinkingText, {"delta": "d"}),
    (StreamText, {"delta": "d"}),
    (ToolUseEvent, {"call": CALL}),
    (ToolResultEvent, {"call": CALL, "result": RESULT}),
    (PermissionRequest, {"call": CALL}),
    (PermissionResponse, {"call": CALL, "decision": Allow()}),
    (RetryEvent, {"attempt": 2, "reason": "timeout"}),
    (UsageEvent, {"usage": USAGE}),
    (CompactStarted, {"reason": "budget", "tokens_before": 100}),
    (CompactNotification, {"summary": "...", "tokens_after": 50}),
    (TurnComplete, {"turn_id": "t", "usage": USAGE}),
    (TurnCommitted, {"turn_id": "t", "text": "hello", "session_id": "s"}),
    (LoopComplete, {"session_id": "s"}),
    (ErrorEvent, {"error": ValueError("x"), "phase": "turn"}),
    (HookEvent, {"hook_id": "h1", "event": "pre_tool_use", "output": "", "success": True}),
    (BudgetBreached, {"dimension": "turns", "reason": "超过轮次上限"}),
)


@pytest.mark.parametrize(("event_type", "fields"), SAMPLES)
def test_event_constructs_with_keyword_fields(event_type: type[Event], fields: dict[str, Any]):
    assert isinstance(event_type(**fields), Event)


def test_events_are_frozen():
    event = TurnStarted(session_id="s", input="hi")
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.input = "changed"  # type: ignore[misc]


def test_baseline_vocabulary_is_seventeen_events():
    assert len(SAMPLES) == 17
