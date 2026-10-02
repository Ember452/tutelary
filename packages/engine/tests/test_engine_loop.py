"""loop.py：回合事件序、记忆注入、工具执行回喂与拒绝路径。"""

from collections.abc import Mapping

from tutelary.core.events import (
    ErrorEvent,
    LLMEvent,
    PermissionResponse,
    StreamText,
    ToolResultEvent,
    ToolUseEvent,
    TurnCommitted,
    UsageEvent,
)
from tutelary.core.fakes import FakeMemory, FakeProvider
from tutelary.core.types import (
    Allow,
    Decision,
    Deny,
    MemoryScope,
    ToolCall,
    ToolResult,
    ToolSpec,
    Usage,
)
from tutelary.engine.loop import Engine, EngineConfig

_SESSION = "s1"


class _ScriptBelt:
    """测试工具带：execute 按名字回放预设输出。"""

    def __init__(self, results: Mapping[str, str]) -> None:
        self._results = dict(results)
        self.executed: list[ToolCall] = []

    def specs(self) -> tuple[ToolSpec, ...]:
        return tuple(ToolSpec(name=name, description="测试工具") for name in self._results)

    async def execute(self, call: ToolCall) -> ToolResult:
        self.executed.append(call)
        return ToolResult(call_id=call.id, output=self._results[call.name])


class _AllowPolicy:
    def check(self, call: ToolCall) -> Decision:
        return Allow()


class _DenyPolicy:
    def check(self, call: ToolCall) -> Decision:
        return Deny(reason="不允许")


def _engine(
    provider: FakeProvider,
    policy: object = None,
    results: Mapping[str, str] | None = None,
    **config: object,
) -> Engine:
    return Engine(
        provider,
        _ScriptBelt(results or {}),
        policy or _AllowPolicy(),  # type: ignore[arg-type]
        FakeMemory(),
        config=EngineConfig(**config),  # type: ignore[arg-type]
    )


def _call(cid: str = "c1") -> ToolCall:
    return ToolCall(id=cid, name="read_file", arguments={"path": "a.md"})


def _tool_turn(cid: str = "c1") -> list[LLMEvent]:
    return [ToolUseEvent(call=_call(cid))]


async def test_plain_text_turn_yields_events_in_order():
    provider = FakeProvider(
        [StreamText(delta="你好"), UsageEvent(usage=Usage(input_tokens=5, output_tokens=2))]
    )
    events = [event async for event in _engine(provider).run(_SESSION, "hi")]
    kinds = [type(e).__name__ for e in events]
    assert kinds == [
        "TurnStarted",
        "StreamText",
        "UsageEvent",
        "TurnCommitted",
        "TurnComplete",
        "LoopComplete",
    ]
    committed = events[3]
    assert isinstance(committed, TurnCommitted)
    assert committed.text == "你好" and committed.session_id == _SESSION


async def test_memory_recall_is_injected_as_system_prefix():
    memory = FakeMemory()
    memory.seed(
        MemoryScope(agent_id="agent", session_id=_SESSION), "历史记忆：hi 之前聊过预算 100k"
    )
    provider = FakeProvider([StreamText(delta="好")])
    engine = Engine(provider, _ScriptBelt({}), _AllowPolicy(), memory)
    async for _ in engine.run(_SESSION, "hi"):
        pass
    first_request = provider.requests[0]
    assert first_request.messages[0].role == "system"
    assert "预算 100k" in first_request.messages[0].content[0].text  # type: ignore[union-attr]


async def test_tool_call_is_executed_and_results_feed_back():
    provider = FakeProvider(_tool_turn(), [StreamText(delta="完成")])
    belt_results = {"read_file": "文件内容"}
    events = [
        event async for event in _engine(provider, results=belt_results).run(_SESSION, "读一下")
    ]

    kinds = [type(e).__name__ for e in events]
    assert "PermissionRequest" in kinds and "PermissionResponse" in kinds
    assert "ToolResultEvent" in kinds and "TurnComplete" in kinds
    tool_event = next(e for e in events if isinstance(e, ToolResultEvent))
    assert tool_event.result.output == "文件内容"

    # 结果以 tool 角色回喂给下一轮请求
    second_request = provider.requests[1]
    tool_message = [m for m in second_request.messages if m.role == "tool"]
    assert tool_message and tool_message[0].content[0].result.output == "文件内容"  # type: ignore[union-attr]


async def test_deny_produces_error_result_without_execution():
    provider = FakeProvider(_tool_turn(), [StreamText(delta="好")])
    engine = _engine(provider, policy=_DenyPolicy(), results={"read_file": "不应执行"})
    events = [event async for event in engine.run(_SESSION, "hi")]
    response = next(e for e in events if isinstance(e, PermissionResponse))
    assert isinstance(response.decision, Deny)
    tool_event = next(e for e in events if isinstance(e, ToolResultEvent))
    assert tool_event.result.is_error is True
    assert "被拒绝" in tool_event.result.output


async def test_tool_hops_exceeded_yields_typed_error_event():
    # 10 轮全是工具调用，预算 2 轮 → 引擎报错并以 ErrorEvent 收尾
    provider = FakeProvider(*(_tool_turn(f"c{i}") for i in range(10)))
    engine = _engine(provider, results={"read_file": "内容"}, max_tool_hops=2)
    events = [event async for event in engine.run(_SESSION, "hi")]
    assert isinstance(events[-1], ErrorEvent)
    assert isinstance(events[-1].error, Exception)
    assert "上限" in str(events[-1].error)


async def test_history_and_replace_history_expose_session_state():
    provider = FakeProvider([StreamText(delta="好")])
    engine = _engine(provider)
    assert engine.history(_SESSION) == []
    async for _ in engine.run(_SESSION, "hi"):
        pass
    assert engine.history(_SESSION)[0].role == "user"
    engine.replace_history(_SESSION, [])
    assert engine.history(_SESSION) == []
