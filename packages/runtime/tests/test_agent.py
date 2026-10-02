"""Agent 门面：Bus 桥接接通记忆写路径、治理接线、工具带与预设装配。"""

import sys
import tempfile
from pathlib import Path

import pytest

from tutelary.context import Budget, ContextGovernor
from tutelary.core.events import StreamText, TurnCommitted
from tutelary.core.fakes import FakeBus, FakeProvider
from tutelary.core.types import MemoryScope, ToolCall, ToolResult, ToolSpec
from tutelary.memory import MarkdownMemoryConfig, MarkdownProvider
from tutelary.runtime import Agent, ExecTool, Toolbelt
from tutelary.sandbox import SubprocessRuntime

_SESSION = "s1"


class _EchoTool:
    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(name="echo_tool", description="t")

    async def execute(self, call: ToolCall) -> ToolResult:
        return ToolResult(call_id=call.id, output="工具输出")


def _agent(**overrides: object) -> Agent:
    kwargs: dict[str, object] = {
        "provider": FakeProvider([StreamText(delta="回答")]),
        "tools": [_EchoTool()],
    }
    kwargs.update(overrides)
    return Agent(**kwargs)  # type: ignore[arg-type]


def test_toolbelt_routes_by_name_and_flags_unknowns():
    belt = Toolbelt([_EchoTool()])
    assert [spec.name for spec in belt.specs()] == ["echo_tool"]


async def test_toolbelt_execute_routes_and_flags_unknowns():
    belt = Toolbelt([_EchoTool()])
    ok = await belt.execute(ToolCall(id="c1", name="echo_tool"))
    assert ok.output == "工具输出"
    missing = await belt.execute(ToolCall(id="c2", name="nope"))
    assert missing.is_error is True
    assert "未知工具" in missing.output


async def test_exec_tool_runs_command_through_the_subprocess_sandbox():
    tool = ExecTool(SubprocessRuntime())
    call = ToolCall(
        id="c1",
        name="run_command",
        arguments={"command": [sys.executable, "-c", "print('sandboxed')"]},
    )
    result = await tool.execute(call)
    assert result.is_error is False
    assert "sandboxed" in result.output


async def test_exec_tool_rejects_missing_command():
    tool = ExecTool(SubprocessRuntime())
    result = await tool.execute(ToolCall(id="c1", name="run_command", arguments={}))
    assert result.is_error is True
    assert "command" in result.output


async def test_events_bridge_onto_the_bus_lighting_up_memory_write():
    with tempfile.TemporaryDirectory() as tmp:
        bus = FakeBus()
        memory = MarkdownProvider(bus, config=MarkdownMemoryConfig(root=Path(tmp) / "memory"))
        agent = _agent(memory=memory, bus=bus)
        events = [event async for event in agent.run("hi", session_id=_SESSION)]
        assert "TurnCommitted" in [type(event).__name__ for event in events]
        hits = await memory.recall("回答", MemoryScope(agent_id="agent", session_id=_SESSION))
        assert len(hits) == 1  # 事件桥接 → TurnCommitted → 记忆落盘


async def test_governor_is_wired_and_report_is_available():
    governor = ContextGovernor(FakeProvider([]), FakeBus(), config=Budget(total=4000))
    agent = _agent(governor=governor)
    async for _ in agent.run("hi", session_id=_SESSION):
        pass
    report = agent.report()
    assert report is not None
    assert report.budget.total == 4000


def test_from_config_builds_agent_without_network():
    agent = Agent.from_config(
        {
            "provider": {
                "type": "openai-compatible",
                "base_url": "http://test",
                "api_key": "k",
                "model": "m",
            },
            "policy": {"allow": ["run_command"]},
        }
    )
    assert isinstance(agent, Agent)


def test_from_config_rejects_unknown_provider_type():
    with pytest.raises(ValueError, match="未知 provider"):
        Agent.from_config({"provider": {"type": "nope"}})


async def test_turn_committed_event_reaches_observers():
    bus = FakeBus()
    seen: list[str] = []

    async def on_committed(event: TurnCommitted) -> None:
        seen.append(event.text)

    bus.observe(TurnCommitted, on_committed)
    agent = _agent(bus=bus)
    async for _ in agent.run("hi", session_id=_SESSION):
        pass
    assert seen == ["回答"]
