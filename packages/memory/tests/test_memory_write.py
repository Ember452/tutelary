"""MarkdownProvider 写路径：TurnCommitted 落盘、幂等与会话过滤。"""

from pathlib import Path

from tutelary.core.events import TurnCommitted
from tutelary.core.fakes import FakeBus
from tutelary.core.lifecycle import run_disposable
from tutelary.core.types import MemoryScope
from tutelary.memory.provider import MarkdownMemoryConfig, MarkdownProvider


def _provider(tmp_path: Path) -> tuple[MarkdownProvider, FakeBus]:
    bus = FakeBus()
    provider = MarkdownProvider(bus, config=MarkdownMemoryConfig(root=tmp_path))
    return provider, bus


async def test_turn_committed_is_persisted_and_visible(tmp_path: Path):
    provider, bus = _provider(tmp_path)
    provider.setup()
    await bus.emit(TurnCommitted(turn_id="t1", text="记住这个决定", session_id="s1"))
    hits = await provider.recall("决定", MemoryScope(agent_id="a1", session_id="s1"))
    assert [hit.text for hit in hits] == ["记住这个决定"]


async def test_duplicate_turn_committed_is_idempotent(tmp_path: Path):
    provider, bus = _provider(tmp_path)
    provider.setup()
    event = TurnCommitted(turn_id="t1", text="内容", session_id="s1")
    await bus.emit(event)
    await bus.emit(event)
    hits = await provider.recall("内容", MemoryScope(agent_id="a1"))
    assert len(hits) == 1


async def test_event_memory_respects_session_scope(tmp_path: Path):
    provider, bus = _provider(tmp_path)
    provider.setup()
    await bus.emit(TurnCommitted(turn_id="t1", text="会话内的记忆", session_id="s1"))
    other_session = await provider.recall("记忆", MemoryScope(agent_id="a1", session_id="s9"))
    assert other_session == []
    agent_wide = await provider.recall("记忆", MemoryScope(agent_id="a1"))
    assert len(agent_wide) == 1


async def test_dispose_stops_writing(tmp_path: Path):
    provider, bus = _provider(tmp_path)
    dispose = provider.setup()
    assert dispose is not None
    await run_disposable(dispose)
    await bus.emit(TurnCommitted(turn_id="t2", text="退订后的内容", session_id="s1"))
    assert await provider.recall("退订后", MemoryScope(agent_id="a1")) == []
