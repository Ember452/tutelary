"""Mem0Adapter：注入 fake client 的离线测试——映射、作用域、幂等、不可用错误。"""

import sys

import pytest
from tutelary_mem0_adapter.errors import Mem0UnavailableError
from tutelary_mem0_adapter.provider import Mem0Adapter

from tutelary.core.events import TurnCommitted
from tutelary.core.fakes import FakeBus
from tutelary.core.types import MemoryScope

_SCOPE_A = MemoryScope(agent_id="agent-a", session_id="s1")
_SCOPE_B = MemoryScope(agent_id="agent-b", session_id="s1")


class _FakeMem0:
    """mem0.Memory 的形状替身：add/search 记录调用，按 user_id 隔离。"""

    def __init__(self) -> None:
        self.added: list[tuple[list[dict[str, str]], str]] = []
        self.store: dict[str, list[dict[str, object]]] = {}

    def add(
        self, messages: list[dict[str, str]], user_id: str | None = None, **kwargs: object
    ) -> dict[str, object]:
        self.added.append((messages, user_id or ""))
        mid = f"m-{len(self.added)}"
        self.store.setdefault(user_id or "", []).append(
            {"id": mid, "memory": messages[0]["content"], "score": 0.9}
        )
        return {"results": [{"id": mid}]}

    def search(
        self, query: str, user_id: str | None = None, limit: int | None = None, **kwargs: object
    ) -> dict[str, object]:
        rows = [row for row in self.store.get(user_id or "", []) if query in str(row["memory"])]
        return {"results": rows[: limit or 5]}


def _adapter(client: _FakeMem0 | None = None) -> tuple[Mem0Adapter, FakeBus, _FakeMem0]:
    client = client if client is not None else _FakeMem0()
    bus = FakeBus()
    return Mem0Adapter(bus, client=client), bus, client


async def test_seed_then_recall_hits_same_scope():
    adapter, _bus, _client = _adapter()
    adapter.seed(_SCOPE_A, "部署窗口定在周五。")
    hits = await adapter.recall("部署", _SCOPE_A)
    assert [hit.text for hit in hits] == ["部署窗口定在周五。"]
    assert hits[0].score == pytest.approx(0.9)


async def test_scopes_map_to_mem0_user_id():
    adapter, _bus, client = _adapter()
    adapter.seed(_SCOPE_A, "agent-a 的秘密")
    assert await adapter.recall("秘密", _SCOPE_B) == []  # user_id 隔离
    assert client.added[0][1] == "agent-a"


async def test_no_hit_returns_empty_without_error():
    adapter, _bus, _client = _adapter()
    adapter.seed(_SCOPE_A, "别的内容")
    assert await adapter.recall("绝对不存在", _SCOPE_A) == []


async def test_turn_committed_write_is_idempotent():
    adapter, bus, client = _adapter()
    adapter.setup()
    event = TurnCommitted(turn_id="t1", text="事件写入的记忆", session_id="s1")
    await bus.emit(event)
    await bus.emit(event)
    assert len(client.added) == 1  # 重复派发不重复 add
    assert client.added[0][1] == "s1"  # 事件写路径 user_id = session


async def test_dispose_stops_writing():
    adapter, bus, client = _adapter()
    dispose = adapter.setup()
    assert dispose is not None
    from tutelary.core.lifecycle import run_disposable

    await run_disposable(dispose)
    await bus.emit(TurnCommitted(turn_id="t2", text="退订后", session_id="s1"))
    assert client.added == []


async def test_missing_mem0_sdk_raises_typed_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setitem(sys.modules, "mem0", None)  # 强制"SDK 未安装"路径
    adapter = Mem0Adapter(FakeBus())  # 不注入 client，走惰性导入路径
    with pytest.raises(Mem0UnavailableError, match="mem0ai 未安装"):
        await adapter.recall("任意", _SCOPE_A)
