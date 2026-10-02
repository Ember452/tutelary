"""Suspend 断点续跑：停驻保存待批调用，resume 按审批决定继续。"""

from collections.abc import Mapping

from tutelary.core.events import PermissionResponse, StreamText, ToolResultEvent, ToolUseEvent
from tutelary.core.fakes import FakeMemory, FakeProvider
from tutelary.core.types import Allow, Decision, Deny, Suspend, ToolCall, ToolResult, ToolSpec
from tutelary.engine.errors import NoPendingTurnError
from tutelary.engine.loop import Engine

_SESSION = "s1"


class _ScriptBelt:
    def __init__(self, results: Mapping[str, str]) -> None:
        self._results = dict(results)
        self.executed: list[ToolCall] = []

    def specs(self) -> tuple[ToolSpec, ...]:
        return tuple(ToolSpec(name=name, description="t") for name in self._results)

    async def execute(self, call: ToolCall) -> ToolResult:
        self.executed.append(call)
        return ToolResult(call_id=call.id, output=self._results[call.name])


class _SuspendPolicy:
    def check(self, call: ToolCall) -> Decision:
        return Suspend(prompt=f"审批 {call.name}")


def _engine(results: Mapping[str, str]) -> Engine:
    provider = FakeProvider(
        [ToolUseEvent(call=ToolCall(id="c1", name="read_file", arguments={"path": "a"}))],
        [StreamText(delta="审批后完成")],
    )
    return Engine(provider, _ScriptBelt(results), _SuspendPolicy(), FakeMemory())


async def test_suspend_parks_the_pending_call():
    engine = _engine({"read_file": "文件内容"})
    events = [e async for e in engine.run(_SESSION, "读")]
    kinds = [type(e).__name__ for e in events]
    assert "PermissionRequest" in kinds and "PermissionResponse" in kinds
    assert "TurnComplete" not in kinds and "LoopComplete" not in kinds
    response = next(e for e in events if isinstance(e, PermissionResponse))
    assert isinstance(response.decision, Suspend)


async def test_resume_with_approval_completes_the_turn():
    engine = _engine({"read_file": "文件内容"})
    async for _ in engine.run(_SESSION, "读"):
        pass
    events = [e async for e in engine.resume(_SESSION, decisions={"c1": True})]
    kinds = [type(e).__name__ for e in events]
    assert "TurnCommitted" in kinds and "TurnComplete" in kinds and "LoopComplete" in kinds
    response = next(e for e in events if isinstance(e, PermissionResponse))
    assert isinstance(response.decision, Allow)
    tool_event = next(e for e in events if isinstance(e, ToolResultEvent))
    assert tool_event.result.output == "文件内容"


async def test_resume_with_denial_feeds_deny_result():
    engine = _engine({"read_file": "不应执行"})
    async for _ in engine.run(_SESSION, "读"):
        pass
    events = [e async for e in engine.resume(_SESSION, decisions={"c1": False})]
    tool_event = next(e for e in events if isinstance(e, ToolResultEvent))
    assert tool_event.result.is_error is True
    assert "审批未通过" in tool_event.result.output
    assert "TurnComplete" in [type(e).__name__ for e in events]


async def test_resume_without_pending_raises():
    engine = _engine({})
    try:
        async for _ in engine.resume(_SESSION, decisions={}):
            pass
    except NoPendingTurnError:
        pass
    else:
        raise AssertionError("无挂起回合的 resume 应抛 NoPendingTurnError")
