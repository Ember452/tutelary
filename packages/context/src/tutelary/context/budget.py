"""预算声明：一次运行花多少、花在哪（docs/01 §3 的"预算分配"）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from tutelary.context.errors import ContextBudgetError

type Section = Literal["system", "history", "tools", "memory", "reserve"]

SECTIONS: tuple[Section, ...] = ("system", "history", "tools", "memory", "reserve")

DEFAULT_TOTAL_TOKENS = 8000
"""开箱默认预算：量级参考（8B 级模型常用上下文的保守档），使用方显式声明为准。"""


@dataclass(frozen=True, slots=True)
class Budget:
    """token 预算：总预算 + 各段份额（和必须为 1，构造期 fail fast）。

    system / history 是实测段——消息直接落在这里，治理器量得到；
    tools / memory / reserve 是声明段——留给工具规格、召回内容与
    输出的额度，由循环方遵守，内省报告按"预留"呈现。
    """

    total: int = DEFAULT_TOTAL_TOKENS
    system: float = 0.10
    history: float = 0.60
    tools: float = 0.10
    memory: float = 0.10
    reserve: float = 0.10

    def __post_init__(self) -> None:
        if self.total <= 0:
            raise ContextBudgetError(f"预算必须为正，得到 {self.total}")
        drift = abs(sum(getattr(self, name) for name in SECTIONS) - 1.0)
        if drift > 1e-9:
            raise ContextBudgetError(f"份额之和必须为 1.0，偏差 {drift}")

    def section_tokens(self, section: Section) -> int:
        """该段的 token 额度。"""
        return int(getattr(self, section) * self.total)


class BudgetConfig:
    """Budget 的鸭子配置协议适配：model_validate(dict) → Budget（AGENTS 兼容 pydantic 协议）。"""

    @classmethod
    def model_validate(cls, data: dict[str, object]) -> Budget:
        try:
            return Budget(**data)  # type: ignore[arg-type]
        except TypeError as exc:
            raise ValueError(f"非法预算字段：{exc}") from exc
