"""memory 基准（docs/07 M4 基准套件 v0）：接契约的实现一键跑分、结果可复现。

工作负载是确定性的：固定的种子记忆集 + 固定查询集（含多命中与无命中
边界、含 agent 隔离用例），对任意 Memory 实现跑 repeats 轮。指标：

- recall_hit_rate：期望命中的记忆在召回结果中全部出现的查询占比；
- mean_precision：召回结果中相关项的占比（防"全召回刷分"）；
- scope_isolation_ok：agent 作用域互不串扰；
- 延迟取 recall 单次的 p50/p95（不同实现存储介质不同，只作参考不进验收）。

被测实现需暴露 ``seed(scope, text) -> str`` 播种面（docs/04 §4）。
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from tutelary.core.types import MemoryScope


@dataclass(frozen=True, slots=True)
class WorkloadCase:
    """确定性工作负载：种子记忆（key, agent, text）与查询（agent, query, 期望 keys）。"""

    name: str
    memories: tuple[tuple[str, str, str], ...]
    queries: tuple[tuple[str, str, tuple[str, ...]], ...]


DEFAULT_WORKLOAD = WorkloadCase(
    name="memory-workload-v0",
    memories=(
        ("deploy-window", "agent-a", "部署窗口定在周五上午十点，失败则回滚到 v1.2。"),
        ("db-migration", "agent-a", "数据库迁移安排在周四凌晨两点执行。"),
        ("budget", "agent-a", "本月 token 预算上限是八千，超出需要审批。"),
        ("gray-release", "agent-a", "灰度发布从百分之五流量开始，观察两小时。"),
        ("oncall", "agent-b", "值班同学是张三，升级路径先电话后工单，响应时间要求五分钟。"),
        ("meeting", "agent-b", "周会时间改为周三下午三点，同步进度用看板。"),
    ),
    queries=(
        ("agent-a", "回滚", ("deploy-window",)),
        ("agent-a", "迁移", ("db-migration",)),
        ("agent-a", "预算", ("budget",)),
        ("agent-a", "灰度", ("gray-release",)),
        ("agent-a", "安排", ("db-migration",)),
        ("agent-b", "值班", ("oncall",)),
        ("agent-b", "时间", ("oncall", "meeting")),  # 多命中
        ("agent-a", "不存在的关键词", ()),  # 无命中边界
    ),
)

_SCOPE_SESSION = "bench"


@dataclass(frozen=True)
class BenchmarkResult:
    """一次跑分的完整账目（JSON 可序列化）。"""

    implementation: str
    workload: str
    repeats: int
    recall_hit_rate: float
    mean_precision: float
    scope_isolation_ok: bool
    latency_p50_ms: float
    latency_p95_ms: float
    per_query: tuple[dict[str, Any], ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "implementation": self.implementation,
            "workload": self.workload,
            "repeats": self.repeats,
            "metrics": {
                "recall_hit_rate": self.recall_hit_rate,
                "mean_precision": self.mean_precision,
                "scope_isolation_ok": self.scope_isolation_ok,
                "latency_p50_ms": self.latency_p50_ms,
                "latency_p95_ms": self.latency_p95_ms,
            },
            "per_query": list(self.per_query),
        }


async def run_benchmark(
    factory: Callable[[], Any],
    *,
    implementation: str,
    workload: WorkloadCase = DEFAULT_WORKLOAD,
    repeats: int = 3,
) -> BenchmarkResult:
    """对 factory 给出的实现跑 repeats 轮；factory 每轮返回**全新**实例。"""
    if repeats < 1:
        raise ValueError(f"repeats 必须 >= 1，得到 {repeats}")
    latencies: list[float] = []
    per_query: dict[str, dict[str, Any]] = {}
    isolation_ok = True

    for _ in range(repeats):
        impl = factory()
        for _key, agent, text in workload.memories:
            impl.seed(_scope(agent), text)
        for agent, query, expected in workload.queries:
            started = time.perf_counter()
            hits = await impl.recall(query, _scope(agent))
            elapsed_ms = (time.perf_counter() - started) * 1000
            latencies.append(elapsed_ms)
            hit_texts = "\n".join(hit.text for hit in hits)
            missing = [k for k in expected if workload_text(workload, k) not in hit_texts]
            row = per_query.setdefault(
                query,
                {
                    "query": query,
                    "expected": list(expected),
                    "hit_rate_passes": 0,
                    "precisions": [],
                },
            )
            if not missing:
                row["hit_rate_passes"] += 1
            if expected:
                relevant = sum(
                    1
                    for hit in hits
                    if any(workload_text(workload, k) in hit.text for k in expected)
                )
                precision = relevant / len(hits) if hits else 0.0
            else:
                precision = 1.0 if not hits else 0.0  # 无命中查询：返回空即满分
            row["precisions"].append(precision)
            if query == "不存在的关键词" and hits:
                isolation_ok = False

    # 隔离性：agent-a 的查询绝不应带出 agent-b 的种子（反向同理）
    impl = factory()
    for _key, agent, text in workload.memories:
        impl.seed(_scope(agent), text)
    cross = await impl.recall("灰度", _scope("agent-b"))
    if any("灰度" in hit.text for hit in cross):
        isolation_ok = False

    # hit_rate 只统计有期望命中的查询；无命中边界单独按"返回空"计 precision
    meaningful = [row for row in per_query.values() if row["expected"]]
    hit_rate = (
        sum(1 for row in meaningful if row["hit_rate_passes"] == repeats) / len(meaningful)
        if meaningful
        else 1.0
    )
    precisions = [p for row in per_query.values() for p in row["precisions"]]
    ordered = sorted(latencies)
    p50 = ordered[len(ordered) // 2] if ordered else 0.0
    p95 = ordered[int(len(ordered) * 0.95)] if ordered else 0.0

    return BenchmarkResult(
        implementation=implementation,
        workload=workload.name,
        repeats=repeats,
        recall_hit_rate=hit_rate,
        mean_precision=sum(precisions) / len(precisions) if precisions else 1.0,
        scope_isolation_ok=isolation_ok,
        latency_p50_ms=round(p50, 3),
        latency_p95_ms=round(p95, 3),
        per_query=tuple(
            {
                "query": row["query"],
                "expected": row["expected"],
                "hit_rate_passes": row["hit_rate_passes"],
                "precision_mean": round(sum(row["precisions"]) / len(row["precisions"]), 4),
            }
            for row in per_query.values()
        ),
    )


def workload_text(workload: WorkloadCase, key: str) -> str:
    for entry_key, _agent, text in workload.memories:
        if entry_key == key:
            return text
    raise KeyError(f"workload 中不存在记忆 {key!r}")


def _scope(agent: str) -> MemoryScope:
    return MemoryScope(agent_id=agent, session_id=_SCOPE_SESSION)


def run_benchmark_sync(factory: Callable[[], Any], **kwargs: Any) -> BenchmarkResult:
    """CLI 入口：同步包装。"""
    return asyncio.run(run_benchmark(factory, **kwargs))
