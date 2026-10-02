"""FakeMemory：种子召回、无命中不抛错、事件写路径幂等。"""

from tutelary.core.events import TurnCommitted
from tutelary.core.fakes import FakeBus, FakeMemory
from tutelary.core.types import MemoryScope


async def test_seed_then_recall_hits():
    memory = FakeMemory()
    memory.seed(MemoryScope(agent_id="a1", session_id="s1"), "部署在周五")
    hits = await memory.recall("周五", MemoryScope(agent_id="a1", session_id="s1"))
    assert [hit.text for hit in hits] == ["部署在周五"]


async def test_recall_other_scope_returns_empty_without_error():
    memory = FakeMemory()
    memory.seed(MemoryScope(agent_id="a1"), "秘密")
    assert await memory.recall("秘密", MemoryScope(agent_id="a2")) == []


async def test_empty_query_recalls_everything_in_scope():
    memory = FakeMemory()
    memory.seed(MemoryScope(agent_id="a1"), "one")
    memory.seed(MemoryScope(agent_id="a1"), "two")
    assert len(await memory.recall("", MemoryScope(agent_id="a1"))) == 2


async def test_load_context_contains_seed_text():
    memory = FakeMemory()
    memory.seed(MemoryScope(agent_id="a1"), "预算 100k")
    context = await memory.load_context("预算", MemoryScope(agent_id="a1"))
    assert "预算 100k" in context


async def test_turn_committed_write_path_is_idempotent():
    memory = FakeMemory()
    bus = FakeBus()
    memory.bind(bus)
    event = TurnCommitted(turn_id="t1", text="记住这个", session_id="s1")
    await bus.emit(event)
    await bus.emit(event)
    hits = await memory.recall("记住", MemoryScope(agent_id="a1", session_id="s1"))
    assert len(hits) == 1
