"""ApprovalGate：审批门——命中的工具一律 Suspend，等待人工批准。"""

from __future__ import annotations

from tutelary.core.types import Allow, Decision, Suspend, ToolCall

DEFAULT_PROMPT_TEMPLATE = "工具 {tool} 需要人工审批后才能执行"
"""Suspend.prompt 面向用户可展示（docs/04 §2）；可用 prompt_template 覆盖。"""


class ApprovalGate:
    """把指定工具（缺省为全部工具）判成 Suspend。

    docs/03 §4 的 Suspend 协议里，"安全停驻 + 审批后断点续跑"是 M3 引擎
    的职责；本类只负责判定侧：产出带可展示 prompt 的 Suspend。未命中
    的工具放行。check 无副作用（docs/04 §2）。
    """

    def __init__(
        self,
        tools: tuple[str, ...] | None = None,
        prompt_template: str = DEFAULT_PROMPT_TEMPLATE,
    ) -> None:
        self._tools = frozenset(tools) if tools is not None else None
        self._prompt_template = prompt_template

    def check(self, call: ToolCall) -> Decision:
        if self._tools is None or call.name in self._tools:
            return Suspend(prompt=self._prompt_template.format(tool=call.name))
        return Allow()
