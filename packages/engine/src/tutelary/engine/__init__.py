"""Tutelary 引擎：事件溯源的异步生成器循环。

消费 Provider / Tool / Policy / Memory 四端口（Sandbox 由沙箱化工具
消费——端口链在整船里全通，见 docs/plans/2026-10-02-m3-tasks.md §2）；
Suspend 挂起经 resume 从断点续跑。引擎只 yield 事件，Bus 桥接由组合根
（runtime 门面）负责。
"""

from tutelary.engine.errors import EngineError, NoPendingTurnError, ToolHopsExceededError

__all__ = ["EngineError", "NoPendingTurnError", "ToolHopsExceededError"]
