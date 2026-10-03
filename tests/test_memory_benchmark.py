"""基准 harness 自测：内置 markdown 实现必须拿满质量分（确定性）。

benchmarks/ 不是 workspace 成员，故先注入 sys.path 再导入——顺序不能反。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.memory.harness import DEFAULT_WORKLOAD, run_benchmark
from benchmarks.memory.run_benchmark import builtin_markdown_factory


async def test_builtin_markdown_achieves_full_quality():
    result = await run_benchmark(
        builtin_markdown_factory, implementation="builtin-markdown", repeats=2
    )
    assert result.recall_hit_rate == 1.0, result.per_query
    assert result.mean_precision >= 0.99, result.per_query
    assert result.scope_isolation_ok is True
    assert result.workload == DEFAULT_WORKLOAD.name


async def test_workload_covers_edge_queries():
    queries = [query for _agent, query, _expected in DEFAULT_WORKLOAD.queries]
    assert "时间" in queries  # 多命中
    assert "不存在的关键词" in queries  # 无命中
