"""卸载：大块工具结果移出上下文，按引用取回（docs/01 §3 的"卸载"）。"""

from __future__ import annotations

from tutelary.context.errors import OffloadMissError


class OffloadStore:
    """内存卸载仓库：原文寄存在这里，消息里只留占位符。

    单事件循环内使用，不加锁；内容随组件实例存亡——持久化是 M2+ 的事
    （对接 Memory 写路径或外部存储再议，见 docs/09 M2）。
    """

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def put(self, ref: str, content: str) -> None:
        """按引用寄存原文；引用通常就是 tool call id。"""
        self._store[ref] = content

    def get(self, ref: str) -> str:
        """按引用取回原文；未命中抛 OffloadMissError。"""
        try:
            return self._store[ref]
        except KeyError:
            raise OffloadMissError(f"卸载引用不存在：{ref}") from None

    def __len__(self) -> int:
        return len(self._store)
