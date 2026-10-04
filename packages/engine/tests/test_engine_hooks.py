"""HookEngine 与引擎接线的意图测试（镜像 FlowCoder hooks 测试关注点）。

覆盖：HookEngine 单元语义（匹配 / once / reject 校验 / 条件谓词）与
引擎八个生命周期点的触发、pre_tool_use 拒绝先于策略、pre_send prompt
注入 system、Hook 异常隔离。
"""

import pytest

from tutelary.core.events import (
    HookEvent,
    LoopComplete,
    StreamText,
    ToolResultEvent,
    ToolUseEvent,
)
from tutelary.core.fakes import FakeMemory, FakeProvider
from tutelary.core.types import (
    Allow,
    Decision,
    TextBlock,
    ToolCall,
    ToolResult,
    ToolSpec,
)
from tutelary.engine.hooks import Hook, HookEngine
from tutelary.engine.loop import Engine


class _Belt:
    def specs(self) -> tuple[ToolSpec, ...]:
        return (ToolSpec(name="read_file", description="t"),)

    async def execute(self, call: ToolCall) -> ToolResult:
        return ToolResult(call_id=call.id, output="文件内容")


class _AllowPolicy:
    def check(self, call: ToolCall) -> Decision:
        return Allow()


def _engine(hooks: HookEngine | None) -> Engine:
    provider = FakeProvider(
        [ToolUseEvent(call=ToolCall(id="c1", name="read_file"))], [StreamText(delta="完成")]
    )
    return Engine(provider, _Belt(), _AllowPolicy(), FakeMemory(), hooks=hooks)


# ---------------------------------------------------------------------------
# HookEngine 单元语义
# ---------------------------------------------------------------------------


async def test_matching_event_fires_in_registration_order():
    engine = HookEngine(
        [
            Hook(name="second", event="pre_send", prompt="两"),
            Hook(name="first", event="pre_send", prompt="一"),
        ]
    )
    outcome = await engine.run("pre_send", {})
    assert [h.name for h in outcome.fired] == ["second", "first"]
    assert outcome.prompts == ["两", "一"]


async def test_other_events_do_not_fire():
    engine = HookEngine([Hook(name="h", event="pre_send", prompt="x")])
    outcome = await engine.run("turn_start", {})
    assert outcome.fired == [] and outcome.prompts == []


async def test_once_fires_only_once():
    engine = HookEngine([Hook(name="h", event="turn_start", prompt="x", once=True)])
    await engine.run("turn_start", {})
    outcome = await engine.run("turn_start", {})
    assert outcome.fired == []


async def test_condition_filters_by_context():
    engine = HookEngine(
        [
            Hook(
                name="h",
                event="pre_tool_use",
                reject=True,
                condition=lambda ctx: ctx.get("tool_name") == "rm",
            )
        ]
    )
    blocked = await engine.run("pre_tool_use", {"tool_name": "rm"})
    assert blocked.rejected is True
    allowed = await engine.run("pre_tool_use", {"tool_name": "read_file"})
    assert allowed.rejected is False


def test_reject_on_other_event_is_rejected_at_construction():
    with pytest.raises(ValueError, match="pre_tool_use"):
        Hook(name="h", event="turn_start", reject=True)


def test_unknown_event_is_rejected_at_construction():
    with pytest.raises(ValueError, match="未知生命周期事件"):
        Hook(name="h", event="mid_turn")


def test_register_returns_disposable():
    engine = HookEngine()
    dispose = engine.register(Hook(name="h", event="pre_send", prompt="x"))
    dispose()
    dispose()  # 幂等
    import asyncio

    assert asyncio.run(engine.run("pre_send", {})).fired == []


# ---------------------------------------------------------------------------
# 引擎接线
# ---------------------------------------------------------------------------


async def test_lifecycle_receipts_appear_in_order():
    engine = _engine(
        HookEngine([Hook(name="obs", event="turn_start"), Hook(name="obs2", event="post_receive")])
    )
    events = [e async for e in engine.run("s1", "hi")]
    kinds = [type(e).__name__ for e in events]
    assert kinds[0] == "TurnStarted"
    receipts = [e for e in events if isinstance(e, HookEvent)]
    # post_receive 每次请求都触发：工具回合 + 最终回答 = 两次
    assert [(r.hook_id, r.event) for r in receipts] == [
        ("obs", "turn_start"),
        ("obs2", "post_receive"),
        ("obs2", "post_receive"),
    ]


async def test_pre_tool_use_reject_blocks_execution_before_policy():
    engine = _engine(HookEngine([Hook(name="guard", event="pre_tool_use", reject=True)]))
    events = [e async for e in engine.run("s1", "hi")]
    result = next(e for e in events if isinstance(e, ToolResultEvent)).result
    assert result.is_error is True
    assert "被 Hook" in result.output


async def test_pre_send_prompt_is_injected_as_system_message():
    provider = FakeProvider([StreamText(delta="好")])
    engine = Engine(
        provider,
        _Belt(),
        _AllowPolicy(),
        FakeMemory(),
        hooks=HookEngine([Hook(name="injector", event="pre_send", prompt="始终保持简洁")]),
    )
    async for _ in engine.run("s1", "hi"):
        pass
    first_request = provider.requests[0]
    system_texts = [
        block.text
        for m in first_request.messages
        if m.role == "system"
        for block in m.content
        if isinstance(block, TextBlock)
    ]
    assert "始终保持简洁" in system_texts


async def test_hook_engine_exception_is_isolated_into_failed_receipt():
    class _ExplodingEngine(HookEngine):
        async def run(self, event, context):  # type: ignore[override]
            raise RuntimeError("hook engine exploded")

    engine = _engine(_ExplodingEngine())
    events = [e async for e in engine.run("s1", "hi")]
    failed = [e for e in events if isinstance(e, HookEvent) and not e.success]
    assert any("exploded" in e.output for e in failed)

    assert isinstance(events[-1], LoopComplete)  # 回合未被阻断
