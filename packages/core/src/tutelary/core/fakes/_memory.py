"""FakeMemory：Memory 端口的内存假实现——种子、子串召回与事件写路径。"""

from __future__ import annotations

from dataclasses import dataclass

from tutelary.core.events import Bus, TurnCommitted
from tutelary.core.lifecycle import Disposable
from tutelary.core.types import MemoryHit, MemoryScope


@dataclass(slots=True)
class _Record:
    id: str
    scope: MemoryScope
    text: str


def _scope_matches(record_scope: MemoryScope, query: MemoryScope) -> bool:
    # 事件写路径不知道 agent，记空串作通配；record 无 session 表示全局可见
    agent_ok = not record_scope.agent_id or record_scope.agent_id == query.agent_id
    session_ok = record_scope.session_id is None or record_scope.session_id == query.session_id
    return agent_ok and session_ok


class FakeMemory:
    """内存记忆：recall 无命中返回空列表不抛错（docs/04 §2）。

    写路径通过 ``bind`` 订阅 ``TurnCommitted``，按 turn_id 幂等消费——
    重复派发同一回合不重复落库。召回是确定性子串匹配，无排序语义
    （score 恒 0）；空 query 召回范围内全部记录。
    """

    def __init__(self) -> None:
        self._records: list[_Record] = []
        self._committed_turns: set[str] = set()
        self._counter = 0

    def seed(self, scope: MemoryScope, text: str) -> str:
        """直接写入一条种子记录（测试与装配预备数据用），返回记录 id。"""
        self._counter += 1
        record = _Record(id=f"fake-{self._counter}", scope=scope, text=text)
        self._records.append(record)
        return record.id

    def bind(self, bus: Bus) -> Disposable:
        """接上事件写路径：订阅 TurnCommitted；Disposable 供 effect 栈登记。"""
        return bus.observe(TurnCommitted, self._on_turn_committed)

    async def recall(self, query: str, scope: MemoryScope) -> list[MemoryHit]:
        """子串召回：query 非空时按包含匹配，命中顺序即写入顺序。"""
        return [
            MemoryHit(id=record.id, text=record.text)
            for record in self._records
            if _scope_matches(record.scope, scope) and (not query or query in record.text)
        ]

    async def load_context(self, query: str, scope: MemoryScope) -> str:
        """召回结果按行拼接；无命中返回空串。"""
        hits = await self.recall(query, scope)
        return "\n".join(hit.text for hit in hits)

    async def _on_turn_committed(self, event: TurnCommitted) -> None:
        if event.turn_id in self._committed_turns:
            return
        self._committed_turns.add(event.turn_id)
        scope = MemoryScope(agent_id="", session_id=event.session_id)
        self.seed(scope, event.text)
