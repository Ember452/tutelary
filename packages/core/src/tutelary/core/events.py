"""事件协议与总线（docs/03 §3、docs/04 §3）。

事件全部 frozen。总线只有两个订阅动词、一个发射动词：observe（异步扇出，
单个 handler 失败被隔离）、intercept（拦截链，可返回新事件替换、返回 None
否决）、emit（先拦截后扇出）。流式增量事件不设拦截——04 §3 的硬规则，
由总线实现在注册时强制。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from tutelary.core.lifecycle import Disposable
from tutelary.core.types import Decision, ToolCall, ToolResult, Usage


@dataclass(frozen=True, slots=True, kw_only=True)
class Event:
    """全部事件的基类；frozen，字段见各子类（docs/04 §3）。"""


@dataclass(frozen=True, slots=True, kw_only=True)
class TurnStarted(Event):
    """回合开始。"""

    session_id: str
    input: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ThinkingText(Event):
    """思维增量。"""

    delta: str


@dataclass(frozen=True, slots=True, kw_only=True)
class StreamText(Event):
    """文本增量。"""

    delta: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolUseEvent(Event):
    """发起工具调用。"""

    call: ToolCall


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolResultEvent(Event):
    """工具返回。"""

    call: ToolCall
    result: ToolResult


@dataclass(frozen=True, slots=True, kw_only=True)
class PermissionRequest(Event):
    """需要判定。"""

    call: ToolCall


@dataclass(frozen=True, slots=True, kw_only=True)
class PermissionResponse(Event):
    """判定完成。"""

    call: ToolCall
    decision: Decision


@dataclass(frozen=True, slots=True, kw_only=True)
class RetryEvent(Event):
    """将要重试。"""

    attempt: int
    reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class UsageEvent(Event):
    """计量。"""

    usage: Usage


@dataclass(frozen=True, slots=True, kw_only=True)
class CompactStarted(Event):
    """压缩开始。"""

    reason: str
    tokens_before: int


@dataclass(frozen=True, slots=True, kw_only=True)
class CompactNotification(Event):
    """压缩完成。"""

    summary: str
    tokens_after: int


@dataclass(frozen=True, slots=True, kw_only=True)
class TurnComplete(Event):
    """回合结束。"""

    turn_id: str
    usage: Usage


@dataclass(frozen=True, slots=True, kw_only=True)
class TurnCommitted(Event):
    """回合内容已落定——记忆写路径的统一消费点（docs/03 §4）。

    实现逼出来的补充：04 §3 基线清单原本漏了它，但 Memory 写路径
    契约依赖这个事件，故补入（工作草案规则，随实现修订）。
    """

    turn_id: str
    text: str
    session_id: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class LoopComplete(Event):
    """运行结束。"""

    session_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ErrorEvent(Event):
    """错误；error 携带异常实例以便按类型分流，phase 标注出错阶段。"""

    error: BaseException
    phase: str


type LLMEvent = ThinkingText | StreamText | ToolUseEvent | UsageEvent
"""Provider 流式输出的载荷事件：顺序跟随 LLM 原始序，Usage 必发（docs/04 §2）。"""


@runtime_checkable
class Bus(Protocol):
    """双语义事件总线的端口语法（参考实现见 ``tutelary.core.fakes.FakeBus``）。

    emit 的契约：先按注册顺序跑 intercept 链——链上可返回新事件替换、
    返回 None 否决——再对**最终事件**按类型并发扇出 observe。否决时
    返回入参原事件，观察者不可见。
    """

    def observe[E: Event](self, et: type[E], handler: Callable[[E], Awaitable[None]]) -> Disposable:
        """扇出订阅：emit 时并发调用；单个 handler 失败被隔离、不传染。"""
        ...

    def intercept[E: Event](
        self, et: type[E], handler: Callable[[E], Awaitable[E | None]]
    ) -> Disposable:
        """拦截订阅（SPI）：可改写、可否决；仅限 SPI 类事件。"""
        ...

    async def emit[E: Event](self, event: E) -> E:
        """先拦截（可改写/否决），后扇出；返回最终事件。"""
        ...
