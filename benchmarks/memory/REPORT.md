# memory 基准对比报告（docs/07 M4 · 基准 v0）

工作负载：`memory-workload-v0`（docs/plans/2026-10-02-m4-tasks.md §2）——六个种子记忆横跨两个 agent 作用域、八条查询（含多命中与无命中边界），固定种子零随机，`repeats` 轮取均值。指标三条机器可判：recall_hit_rate / mean_precision / scope_isolation_ok；延迟仅作参考（不同实现存储介质不同）。

复现方式：

```bash
# 内置实现（本报告数据来源）
uv run python benchmarks/memory/run_benchmark.py \
    --output benchmarks/memory/results/builtin-markdown.json
# Mem0（需要 mem0ai 与 LLM API key——mem0 的记忆抽取本身要调 LLM，Mock 它等于伪造基准）
uv run --extra mem0 python benchmarks/memory/run_benchmark.py \
    --factory tutelary_mem0_adapter.testing:make_mem0_factory \
    --implementation mem0 --output benchmarks/memory/results/mem0.json
```

## 结果

| 指标 | 内置 MarkdownProvider | 官方 Mem0 adapter |
|---|---|---|
| recall_hit_rate | **100%** | ⬜ 待跑分 |
| mean_precision | **100%** | ⬜ 待跑分 |
| scope_isolation_ok | **true** | ⬜ 待跑分 |
| 延迟 p50/p95（参考） | 0.48 / 0.60 ms | ⬜ 待跑分 |
| 外部依赖 | 无（纯 markdown 文件） | mem0ai + LLM API |

内置行数据源：`results/builtin-markdown.json`（本仓库实测，2026-10-02）。

## 读法与边界

- 两条实现的定位不同：Markdown 是**确定性子串召回**，mem0 是 **LLM 抽取式记忆**——本基准量的是"契约兑现程度"（命中、精确、隔离）与操作延迟，不比较记忆质量的上限；后者需要真实负载（与 M1 评测集同源）。
- 同一基准能同时接住两条实现，本身就是"契约中立"的机器证明：内置实现无特权，第三方实现无门槛。
- Mem0 行跑分后本报告随之更新；若适配需要扭曲端口，按 docs/09 M4 的停损走 ADR 修端口——那正是 M4 存在的目的。
