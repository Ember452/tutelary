"""MarkdownProvider：Memory 端口的 markdown 实现（docs/07 M2 的内置实现）。

读路径只做确定性子串召回——向量检索刻意不做，那是第三方 Memory2 的
位置（docs/09 M2 明确不做）。写路径经 ``setup()`` 订阅 TurnCommitted
落盘（docs/03 §4：写路径不进端口，一切经 Bus）。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from tutelary.core.events import Bus
from tutelary.core.lifecycle import Component
from tutelary.core.ports import Memory
from tutelary.core.types import MemoryHit, MemoryScope
from tutelary.memory import store
from tutelary.memory.errors import MarkdownMemoryError

DEFAULT_ROOT = Path("tutelary-memory")
"""未显式配置时的存储根目录（相对当前工作目录，写路径才真正创建）。"""


@dataclass(frozen=True, slots=True)
class MarkdownMemoryConfig:
    """markdown 后端配置；root 是唯一的必配项。"""

    root: Path

    @classmethod
    def model_validate(cls, data: dict[str, object]) -> MarkdownMemoryConfig:
        try:
            config = cls(root=Path(str(data["root"])))
        except (KeyError, TypeError) as exc:
            raise ValueError(f"markdown 记忆配置需要 root：{exc}") from exc
        if config.root.exists() and not config.root.is_dir():
            raise MarkdownMemoryError(f"配置的 root 已存在且不是目录：{config.root}")
        return config


class MarkdownProvider(Component):
    """Memory 端口的文件后端。

    组件声明：provides (Memory,)、requires (Bus,)（写路径订阅）。
    所有磁盘访问经 ``asyncio.to_thread`` 进入，事件循环内不阻塞
    （AGENTS §4.4）；例外是 ``seed``——测试播种面，刻意同步。
    """

    name = "memory-markdown"
    provides = (Memory,)
    requires = (Bus,)
    config_model = MarkdownMemoryConfig

    def __init__(self, bus: Bus, config: MarkdownMemoryConfig | None = None) -> None:
        self._bus = bus
        self._root = config.root if config is not None else DEFAULT_ROOT

    async def recall(self, query: str, scope: MemoryScope) -> list[MemoryHit]:
        """子串召回：query 为空返回范围内全部；无命中返回空列表不抛错。"""
        entries = await asyncio.to_thread(store.read_entries, self._root, scope)
        return [
            MemoryHit(id=store.entry_id(self._root, entry), text=entry.text)
            for entry in entries
            if not query or query in entry.text
        ]

    async def load_context(self, query: str, scope: MemoryScope) -> str:
        """召回结果按空行拼接；无命中返回空串。"""
        hits = await self.recall(query, scope)
        return "\n\n".join(hit.text for hit in hits)

    def seed(self, scope: MemoryScope, text: str) -> str:
        """播种一条记忆（docs/04 §4 的套件测试面）；返回条目 id。

        同步写盘是刻意的：它是测试与预备数据的便利面，不是热路径。
        """
        scope_dir = store.entry_dir(self._root, scope.agent_id, scope.session_id)
        serial = len(list(scope_dir.glob("seed-*.md"))) + 1
        entry = store.MemoryEntry(
            turn_id=f"seed-{serial}",
            agent_id=scope.agent_id,
            session_id=scope.session_id,
            text=text,
        )
        store.write_entry(self._root, entry)
        return store.entry_id(self._root, entry)
