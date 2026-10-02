"""token 内省："这次运行的钱花在哪了"（docs/01 §6 瀑布图与 deep-dive 的底稿）。"""

from __future__ import annotations

from dataclasses import dataclass

from tutelary.context.budget import SECTIONS, Budget
from tutelary.context.compact import CompactionStats


@dataclass(frozen=True, slots=True)
class OffloadRecord:
    """一次卸载的账目。"""

    call_id: str
    tokens: int


@dataclass(frozen=True)
class IntrospectionReport:
    """一次运行的内省快照：实测 / 预留 / 压缩 / 卸载 / LLM 计量。

    由治理器在每次 enforce 后重建——它是值不是窗口，持有旧快照不受
    后续运行影响。
    """

    budget: Budget
    measured: dict[str, int]
    usage_input: int = 0
    usage_output: int = 0
    compactions: tuple[CompactionStats, ...] = ()
    offloads: tuple[OffloadRecord, ...] = ()

    def saved_tokens(self) -> int:
        """压缩与卸载合计省下的 tokens（相对原样进上下文）。"""
        compacted = sum(s.tokens_before - s.tokens_after for s in self.compactions)
        offloaded = sum(record.tokens for record in self.offloads)
        return compacted + offloaded

    def render(self) -> str:
        """渲染文本瀑布图。"""
        lines = [f"== token 内省（预算 {self.budget.total}） =="]
        for section in SECTIONS:
            quota = self.budget.section_tokens(section)
            if section in self.measured:
                lines.append(f"  {section:<8} 实测 {self.measured[section]:>6} / 预算 {quota:>6}")
            else:
                lines.append(f"  {section:<8} 预留 {quota:>6}")
        if self.compactions:
            folded = sum(s.folded_messages for s in self.compactions)
            lines.append(f"  压缩 {len(self.compactions)} 次，折叠 {folded} 条消息")
        if self.offloads:
            lines.append(f"  卸载 {len(self.offloads)} 块工具结果")
        lines.append(f"  合计节省 {self.saved_tokens()} tokens")
        lines.append(f"  LLM 计量：输入 {self.usage_input} / 输出 {self.usage_output}")
        return "\n".join(lines)
