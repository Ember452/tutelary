"""HookEngine：生命周期 Hook 的注册与执行（FlowCoder 对齐 F1）。

生命周期点由引擎负责触发：``session_start`` / ``turn_start`` /
``pre_send`` / ``post_receive`` / ``turn_end`` / ``session_end`` /
``pre_tool_use`` / ``post_tool_use``。Hook 是声明式的：

- ``prompt``：产出文本——pre_send 场景由引擎并入 system 前缀；
- ``reject``：仅 pre_tool_use 有效，阻断工具执行（先于策略判定，FlowCoder
  同序）；
- ``once``：触发一次后失效；``condition``：可选谓词，按上下文过滤。

HookEngine 是引擎的**可选协作者**而非端口——FlowCoder 的 Agent 同样把
hook_engine 作为可选构造参数；默认不注册即零行为。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

HookCondition = Callable[[Mapping[str, Any]], bool]
"""条件谓词：接收上下文（session_id / tool_name / arguments 等），返回是否执行。"""

LIFECYCLE_EVENTS: tuple[str, ...] = (
    "session_start",
    "turn_start",
    "pre_send",
    "post_receive",
    "pre_tool_use",
    "post_tool_use",
    "turn_end",
    "session_end",
)


@dataclass(frozen=True, slots=True)
class Hook:
    """声明式生命周期 Hook。"""

    name: str
    event: str
    prompt: str | None = None
    reject: bool = False
    once: bool = False
    condition: HookCondition | None = None

    def __post_init__(self) -> None:
        if self.event not in LIFECYCLE_EVENTS:
            raise ValueError(f"未知生命周期事件：{self.event!r}（合法：{LIFECYCLE_EVENTS}）")
        if self.reject and self.event != "pre_tool_use":
            raise ValueError("reject 仅在 pre_tool_use 上有效")


@dataclass(slots=True)
class HookOutcome:
    """一次生命周期点触发的聚合结果。

    ``errors`` 收集 Hook 执行异常——隔离语义：不向上抛，但以
    success=False 的回执可观测。
    """

    prompts: list[str] = field(default_factory=list)
    rejected: bool = False
    reject_reason: str = ""
    fired: list[Hook] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class HookEngine:
    """按事件点名执行匹配的 Hook；fire 顺序 = 注册顺序，失败隔离由调用方
    （引擎）负责兜底——Hook 内异常视作该 Hook 失败，不阻断回合。"""

    def __init__(self, hooks: Sequence[Hook] = ()) -> None:
        self._hooks: list[Hook] = list(hooks)

    def register(self, hook: Hook) -> Callable[[], None]:
        """注册一个 Hook；返回退订函数（幂等）。"""
        self._hooks.append(hook)

        def dispose() -> None:
            for index, registered in enumerate(self._hooks):
                if registered is hook:
                    del self._hooks[index]
                    break

        return dispose

    async def run(self, event: str, context: Mapping[str, Any]) -> HookOutcome:
        """触发一个生命周期点；once 的 Hook 触发后自动移除。"""
        outcome = HookOutcome()
        spent: list[Hook] = []
        for hook in list(self._hooks):
            if hook.event != event:
                continue
            if hook.condition is not None and not hook.condition(context):
                continue
            outcome.fired.append(hook)
            if hook.prompt:
                outcome.prompts.append(hook.prompt)
            if hook.reject and event == "pre_tool_use":
                outcome.rejected = True
                outcome.reject_reason = f"被 Hook {hook.name!r} 拒绝"
            if hook.once:
                spent.append(hook)
        for hook in spent:
            self._hooks.remove(hook)
        return outcome
