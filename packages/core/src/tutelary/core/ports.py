"""五端口基线签名（docs/03 §4）。

端口是主导抽象不是全集：引擎的真实协作方（hooks、注入提示、工具结果
安检、子 Agent）在 M3 经 ADR 增长为更多窄接口是预期产出。这里只有
Protocol——实现在组件包，或随 core 发布的 fakes。
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable
from typing import Protocol, runtime_checkable

from tutelary.core.events import LLMEvent
from tutelary.core.types import (
    Decision,
    ExecResult,
    ExecSpec,
    LLMRequest,
    MemoryHit,
    MemoryScope,
    ToolCall,
    ToolResult,
    ToolSpec,
)


@runtime_checkable
class Provider(Protocol):
    """LLM 调用：请求进，流式事件出。"""

    def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]: ...


# Tool 故意不加 runtime_checkable：spec 是属性（数据成员），isinstance 对
# 数据成员协议无意义，结构符合性交给类型检查器与契约套件。


class Tool(Protocol):
    """工具：声明式规格 + 执行。"""

    @property
    def spec(self) -> ToolSpec: ...

    async def execute(self, call: ToolCall) -> ToolResult: ...


@runtime_checkable
class Policy(Protocol):
    """权限判定：可组合；Suspend 触发审批挂起/恢复协议（docs/03 §4）。"""

    def check(self, call: ToolCall) -> Decision: ...


@runtime_checkable
class Memory(Protocol):
    """记忆读路径；写路径不进端口——实现方 requires Bus 并订阅
    TurnCommitted（docs/03 §4）。"""

    async def recall(self, query: str, scope: MemoryScope) -> list[MemoryHit]: ...

    async def load_context(self, query: str, scope: MemoryScope) -> str: ...


@runtime_checkable
class Executor(Protocol):
    """一次隔离执行的句柄：run 执行、aclose 归还资源——用毕必关。"""

    async def run(self, spec: ExecSpec) -> ExecResult: ...

    def aclose(self) -> Awaitable[None]: ...


@runtime_checkable
class Sandbox(Protocol):
    """执行隔离：按规格领取执行器，用毕归还；默认断网（docs/04 §2）。"""

    async def acquire(self, spec: ExecSpec) -> Executor: ...
