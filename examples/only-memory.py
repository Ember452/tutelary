"""only-memory：不依赖引擎，单独使用 memory 组件（M2 验收裁判）。

演示四件事：markdown 文件存储、种子与子串召回、TurnCommitted 事件
写路径（含重复派发幂等）、load_context 拼接——全程离线，文件落在
临时目录。
跑法：``uv run python examples/only-memory.py``
"""

import asyncio
import tempfile
from pathlib import Path

from tutelary.core import FakeBus, MemoryScope, TurnCommitted
from tutelary.memory import MarkdownMemoryConfig, MarkdownProvider


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        bus = FakeBus()
        provider = MarkdownProvider(bus, config=MarkdownMemoryConfig(root=Path(tmp) / "memory"))
        scope = MemoryScope(agent_id="ops-agent", session_id="s1")

        provider.seed(scope, "回滚预案：周五窗口上线，失败则回退到 v1.2。")
        provider.setup()

        event = TurnCommitted(
            turn_id="turn-001", text="数据库迁移在周四凌晨执行。", session_id="s1"
        )
        await bus.emit(event)
        await bus.emit(event)  # 重复派发同一回合：幂等，只落一次
        await bus.emit(TurnCommitted(turn_id="turn-002", text="灰度从 5% 开始。", session_id="s1"))

        hits = await provider.recall("回滚", scope)
        print("召回『回滚』：", [hit.text for hit in hits])
        context = await provider.load_context("", scope)
        print("load_context（空 query = 全部）：")
        for chunk in context.split("\n\n"):
            print("  -", chunk)
        total = len(await provider.recall("", scope))
        assert total == 3, f"应恰好 3 条（1 种子 + 2 回合），得到 {total}"
        print("条目数 OK：3 条（重复派发未重复落盘）")


if __name__ == "__main__":
    asyncio.run(main())
