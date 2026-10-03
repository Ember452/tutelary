"""Mem0Adapter：把 mem0.Memory 适配到 Memory 端口——第二个真实实现。

中立性的机器证明：与内置 MarkdownProvider 走同一端口、同一契约套件、
同一基准。写路径与内置实现同规（订阅 TurnCommitted、按 turn_id 幂等）；
读路径映射 mem0 的 ``search`` 结果（新旧版本返回 dict 包裹或裸列表，
防御性兼容）。mem0 需要外部 LLM——真实调用属用户环境，适配逻辑用
注入客户端离线测试。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from typing import Any

from tutelary.core.events import Bus, TurnCommitted
from tutelary.core.lifecycle import Component, Disposable
from tutelary.core.ports import Memory
from tutelary.core.types import MemoryHit, MemoryScope
from tutelary_mem0_adapter.errors import Mem0UnavailableError

_SEARCH_LIMIT = 8


def _extract_rows(raw: Any) -> list[dict[str, Any]]:
    # mem0 新版本把结果包在 {"results": [...]} 里，旧版本返回裸列表
    if isinstance(raw, dict):
        return list(raw.get("results") or [])
    return list(raw or [])


def _first_id(result: Any) -> str | None:
    rows = _extract_rows(result)
    if rows:
        return str(rows[0].get("id", ""))
    if isinstance(result, dict) and result.get("id"):
        return str(result["id"])
    return None


class Mem0Adapter(Component):
    """Memory 端口的 mem0 后端：recall 走 search，写路径走事件 + add。

    ``client`` 注入已构造好的 mem0.Memory（测试与自定义场景）；
    缺省时惰性导入 mem0ai 并按 ``mem0_config`` 构建——SDK 未安装抛
    Mem0UnavailableError。作用域映射：``MemoryScope.agent_id`` → mem0 的
    ``user_id``；事件写路径的 TurnCommitted 不带 agent，user_id 取
    session（缺省 "shared"）。
    """

    name = "memory-mem0"
    provides = (Memory,)
    requires = (Bus,)

    def __init__(
        self,
        bus: Bus,
        client: Any | None = None,
        mem0_config: Mapping[str, Any] | None = None,
    ) -> None:
        self._bus = bus
        self._client = client
        self._mem0_config = dict(mem0_config) if mem0_config else {"llm": {"provider": "openai"}}
        self._committed: set[str] = set()

    async def recall(self, query: str, scope: MemoryScope) -> list[MemoryHit]:
        """mem0 ``search`` 映射为 MemoryHit；无命中返回空列表不抛错。"""
        client = await asyncio.to_thread(self._ensure_client)
        raw = await asyncio.to_thread(
            client.search, query, user_id=scope.agent_id, limit=_SEARCH_LIMIT
        )
        return [
            MemoryHit(
                id=str(item.get("id", "")),
                text=str(item.get("memory", "")),
                score=float(item.get("score", 0.0)),
            )
            for item in _extract_rows(raw)
        ]

    def seed(self, scope: MemoryScope, text: str) -> str:
        """播种测试面（docs/04 §4）；返回 mem0 的结果标识（尽力提取）。"""
        client = self._ensure_client()
        result = client.add([{"role": "user", "content": text}], user_id=scope.agent_id)
        return _first_id(result) or json.dumps(result, ensure_ascii=False, default=str)

    def setup(self) -> Disposable | None:
        """订阅 TurnCommitted 作为写路径；按 turn_id 幂等，落盘走 to_thread。"""

        async def on_committed(event: TurnCommitted) -> None:
            if event.turn_id in self._committed:
                return
            self._committed.add(event.turn_id)
            client = await asyncio.to_thread(self._ensure_client)
            user_id = event.session_id or "shared"
            await asyncio.to_thread(
                client.add, [{"role": "user", "content": event.text}], user_id=user_id
            )

        return self._bus.observe(TurnCommitted, on_committed)

    def _ensure_client(self) -> Any:
        if self._client is None:
            try:
                # mem0ai 是可选 extra：未安装本身就是被测路径，导入缺失属预期
                from mem0 import Memory  # pyright: ignore[reportMissingImports]
            except ImportError as exc:
                raise Mem0UnavailableError(
                    "mem0ai 未安装：pip install 'tutelary-mem0-adapter[mem0]'"
                ) from exc
            self._client = Memory.from_config(self._mem0_config)
        return self._client
