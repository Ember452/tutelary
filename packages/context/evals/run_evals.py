"""M1 评测运行器：两条机器可判硬指标（docs/plans/2026-10-02-m1-tasks.md §3）。

用法：uv run python packages/context/evals/run_evals.py
cases/ 为空 = 待验收（正常退出）；任一案失败 = 退出码 1。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from tutelary.context import Budget, ContextGovernor
from tutelary.core import (
    FakeBus,
    FakeProvider,
    Message,
    StreamText,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    Usage,
    UsageEvent,
)

CASES_DIR = Path(__file__).resolve().parent / "cases"


def load_cases() -> list[dict[str, Any]]:
    if not CASES_DIR.is_dir():
        return []
    return [
        json.loads(path.read_text(encoding="utf-8")) for path in sorted(CASES_DIR.glob("*.json"))
    ]


def build_messages(case: dict[str, Any]) -> list[Message]:
    return [
        Message(role=entry["role"], content=(TextBlock(text=entry["text"]),))
        for entry in case["transcript"]
    ]


def flatten(messages: list[Message]) -> str:
    parts: list[str] = []
    for message in messages:
        for block in message.content:
            if isinstance(block, TextBlock | ThinkingBlock):
                parts.append(block.text)
            elif isinstance(block, ToolResultBlock):
                parts.append(block.result.output)
    return "\n".join(parts)


async def run_case(case: dict[str, Any]) -> tuple[bool, list[str]]:
    """跑一案，返回（是否全过，失败明细）。只认两条硬指标。"""
    summary = [StreamText(delta="[评测摘要]"), UsageEvent(usage=Usage())]
    governor = ContextGovernor(
        FakeProvider(*([summary] * 16)), FakeBus(), config=Budget(**case["budget"])
    )
    must_survive: list[str] = case["must_survive"]
    result = await governor.enforce(build_messages(case), keep_substrings=must_survive)
    report = governor.report()

    failures: list[str] = []
    history_quota = report.budget.section_tokens("history")
    if report.measured.get("history", 0) > history_quota:
        failures.append(
            f"硬指标①：history 实测 {report.measured.get('history')} 超预算 {history_quota}"
        )
    flat = flatten(result.messages)
    for needle in must_survive:
        if needle not in flat:
            failures.append(f"硬指标②：must-survive 丢失：{needle[:40]}…")
    return not failures, failures


def main() -> int:
    cases = load_cases()
    if not cases:
        print(f"评测集为空：{CASES_DIR} 下没有 case。")
        print("等待真实对话日志——格式见同目录 README.md。这是待验收，不是失败。")
        return 0
    failed = 0
    for case in cases:
        ok, failures = asyncio.run(run_case(case))
        mark = "✓" if ok else "✗"
        print(f"{mark} {case.get('id', case.get('budget', {}).get('total', '?'))}")
        for failure in failures:
            print(f"    {failure}")
        failed += 0 if ok else 1
    print(f"\n{len(cases) - failed}/{len(cases)} 通过")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
