"""RunBudget：一次运行的消耗预算——四维"收敛不击杀"（FlowCoder 对齐 F1）。

与 context.Budget（上下文窗口分段）不同：本类约束**一次运行**的累计
消耗——token（LLM 用量）、轮次、墙钟秒数、美元成本（可选计价）。任一
维度触顶后，引擎注入收敛消息并摘除工具 schema，让回合自然收尾；
BaseException 语义下不存在硬杀。
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from tutelary.core.types import Usage

DEFAULT_CONVERGE_MESSAGE = (
    "运行预算已触及上限（{reason}）。请立即总结当前进展并给出最终回答，不要再尝试调用工具。"
)
"""收敛消息模板：{reason} 为可展示的触顶原因（docs/04 §2 的可展示惯例）。"""


@dataclass(frozen=True, slots=True)
class RunBudget:
    """四维运行预算：至少设置一项上限，构造期 fail fast。"""

    max_total_tokens: int | None = None
    max_turns: int | None = None
    max_seconds: float | None = None
    max_cost_usd: float | None = None
    input_price_per_m: float = 0.0
    """每百万输入 token 的单价（成本维度需要）；不设则成本维度不生效。"""
    output_price_per_m: float = 0.0
    converge_message: str = DEFAULT_CONVERGE_MESSAGE

    def __post_init__(self) -> None:
        limits = (self.max_total_tokens, self.max_turns, self.max_seconds, self.max_cost_usd)
        if all(limit is None for limit in limits):
            raise ValueError("RunBudget 至少要设置一项上限")

    def cost_of(self, usage: Usage) -> float:
        """按累计用量估算成本（未配置单价时恒 0——成本维度随之不生效）。"""
        return (
            usage.input_tokens / 1_000_000 * self.input_price_per_m
            + usage.output_tokens / 1_000_000 * self.output_price_per_m
        )


@dataclass(frozen=True, slots=True)
class Breach:
    """一次触顶：维度名 + 可展示原因。"""

    dimension: str
    reason: str


class RunBudgetState:
    """伴随会话的预算记账：迭代数、起始钟、累计用量。

    挂在会话上而非单次 drive——Suspend 停驻/续跑后预算连续。
    """

    def __init__(self, budget: RunBudget) -> None:
        self._budget = budget
        self.started_at: float = time.monotonic()
        self.iterations = 0
        self.total_usage = Usage()

    def advance(self) -> None:
        """每个循环迭代开始时调用：迭代数 +1。"""
        self.iterations += 1

    def record(self, usage: Usage) -> None:
        """合并一轮 LLM 用量。"""
        self.total_usage = Usage(
            input_tokens=self.total_usage.input_tokens + usage.input_tokens,
            output_tokens=self.total_usage.output_tokens + usage.output_tokens,
        )

    def breach(self) -> Breach | None:
        """检查四维；返回首个触顶维度（优先级：tokens > cost > turns > seconds）。"""
        budget = self._budget
        total = self.total_usage.total_tokens
        if budget.max_total_tokens is not None and total > budget.max_total_tokens:
            return Breach("tokens", f"累计 token {total} 超过上限 {budget.max_total_tokens}")
        cost = budget.cost_of(self.total_usage)
        if (
            budget.max_cost_usd is not None
            and budget.max_cost_usd > 0
            and cost > budget.max_cost_usd
        ):
            return Breach("cost", f"估算成本 ${cost:.4f} 超过上限 ${budget.max_cost_usd:.4f}")
        if budget.max_turns is not None and self.iterations > budget.max_turns:
            return Breach("turns", f"迭代轮数 {self.iterations} 超过上限 {budget.max_turns}")
        elapsed = time.monotonic() - self.started_at
        if budget.max_seconds is not None and elapsed > budget.max_seconds:
            return Breach("seconds", f"运行时长 {elapsed:.1f}s 超过上限 {budget.max_seconds:.1f}s")
        return None

    def converge_message(self, breach: Breach) -> str:
        return self._budget.converge_message.format(reason=breach.reason)
