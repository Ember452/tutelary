"""跑分 CLI：对任意 Memory 实现一键跑分，输出 JSON 与 markdown 报告。

用法：
  uv run python benchmarks/memory/run_benchmark.py                # 内置 markdown 实现
  uv run python benchmarks/memory/run_benchmark.py \\
      --factory my_pkg.tests:make_memory --output results/my.json
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from tutelary.core.fakes import FakeBus
from tutelary.memory import MarkdownMemoryConfig, MarkdownProvider

if __package__ in (None, ""):  # 直接脚本执行：仓库根进 sys.path 以导入 benchmarks 包
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmarks.memory.harness import BenchmarkResult, run_benchmark_sync

HERE = Path(__file__).resolve().parent


def builtin_markdown_factory() -> MarkdownProvider:
    """内置实现工厂：每轮全新临时目录，互不污染。"""
    root = Path(tempfile.mkdtemp(prefix="bench-memory-"))
    return MarkdownProvider(FakeBus(), config=MarkdownMemoryConfig(root=root))


def load_factory(dotted: str) -> Callable[[], Any]:
    module_path, _, attr = dotted.partition(":")
    obj: object = importlib.import_module(module_path)
    for part in attr.split("."):
        obj = getattr(obj, part)
    if not callable(obj):
        raise ValueError(f"--factory 必须指向零参可调用对象，得到 {obj!r}")
    return cast("Callable[[], Any]", obj)


def to_markdown(result: BenchmarkResult) -> str:
    lines = [
        f"## {result.implementation}",
        "",
        f"- workload：`{result.workload}` × {result.repeats} 轮",
        f"- recall_hit_rate：**{result.recall_hit_rate:.0%}**",
        f"- mean_precision：**{result.mean_precision:.0%}**",
        f"- scope_isolation_ok：{result.scope_isolation_ok}",
        f"- 延迟 p50/p95：{result.latency_p50_ms:.2f} / {result.latency_p95_ms:.2f} ms（参考值）",
        "",
        "| query | 期望命中 | hit_rate 通过轮 | precision 均值 |",
        "|---|---|---|---|",
    ]
    for row in result.per_query:
        lines.append(
            f"| {row['query']} | {', '.join(row['expected']) or '（应无结果）'} "
            f"| {row['hit_rate_passes']}/{result.repeats} | {row['precision_mean']:.0%} |"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="memory 契约实现的确定性基准")
    parser.add_argument(
        "--factory",
        default=None,
        help="被测实现的零参工厂（'模块:属性'）；缺省为内置 markdown 实现",
    )
    parser.add_argument("--implementation", default="builtin-markdown", help="结果里的实现名")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", default=str(HERE / "results" / "builtin-markdown.json"))
    args = parser.parse_args()

    if args.factory is None:
        factory: object = builtin_markdown_factory
        implementation = args.implementation
    else:
        factory = load_factory(args.factory)
        implementation = args.implementation

    result = run_benchmark_sync(factory, implementation=implementation, repeats=args.repeats)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(to_markdown(result))
    print(f"\nJSON 已写入：{output}")
    ok = (
        result.recall_hit_rate == 1.0
        and result.mean_precision >= 0.99
        and result.scope_isolation_ok
    )
    print("基准判定：", "通过" if ok else "未达标")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
