# deep-dive：上下文预算治理是怎么做的

> Tutelary deep-dive 首篇。配套代码：`packages/context`；可运行示例：`examples/only-context.py`。

"这次运行为什么花了 80k token？"——生产事故里最常见的追问，也是各框架留给你 DIY 的部分。Tutelary 把上下文治理做成一个独立组件（`tutelary-context`），本文讲清它的四个机制和一条设计底线。

## 一、预算是声明，不是建议

治理从一句声明开始：

```python
from tutelary.context import Budget

budget = Budget(total=8000)  # system/history/tools/memory/reserve 各占份额
```

`Budget` 是 frozen dataclass，构造期即校验份额之和为 1——配置错误死在装配期，不死于第三次运行（fail fast 是全项目的纪律）。`system` 与 `history` 是**实测段**：消息直接落在这里，治理器量得到；`tools` / `memory` / `reserve` 是**声明段**：留给工具规格、召回内容与输出的额度，由循环方遵守，内省报告按"预留"呈现。

## 二、治理发生在哪：一个明确的执行点

```python
result = await governor.enforce(messages, keep_substrings=["回滚预案定在周五窗口执行"])
```

`enforce` 是每次 LLM 调用前的**唯一执行点**，内部固定三步：

1. **卸载**——超过阈值（2000 tokens）的工具结果移出上下文，原文进 `OffloadStore`，消息里只留占位符；按 call_id 随时可取回。大工具输出是上下文腐烂的头号来源，而它们几乎不需要驻留。
2. **压缩**——history 实测超出预算段时触发 `SummarizeFoldStrategy`。
3. **记账**——实测/压缩/卸载全部进内省报告，`CompactStarted` / `CompactNotification` 事件广播到 Bus。

## 三、压缩：把"质量"变成机器可判的承诺

压缩最难的不是删，是**删错**。Tutelary 的 M1 压缩策略（每个版本只做一个策略，docs/09）用两个机制把质量从祈祷变成承诺：

**最老优先折叠**：超出目标的部分折成一段摘要，摘要经 Provider 端口生成——引擎循环的第一次真实端口消费，就发生在压缩上。摘要实际大小生成后才知道，估小了就再把最老的保留消息挪进折叠桶重新生成：正确性优先于调用数。

**must-survive 钉住**：`keep_substrings` 命中的消息**原样保留、位置不动**。这把验收从主观判断变成两条机器可判的硬指标：

1. 压缩后实测 token ≤ 预算声明；
2. must-survive 清单在压缩输出中全部保留。

钉住的部分本身就超预算？抛 `ContextBudgetError`——**不静默丢弃受保护内容，也不交付超预算的上下文**。宁可 fail fast，这是治理组件的诚实。

## 四、内省：瀑布图不是装饰

```text
== token 内省（预算 8000） ==
  system   实测     11 / 预算    800
  history  实测     68 / 预算   4800
  tools    预留    800
  memory   预留    800
  reserve  预留    800
  压缩 1 次，折叠 41 条消息
  卸载 1 块工具结果
  合计节省 28535 tokens
  LLM 计量：输入 0 / 输出 0
```

`report()` 是值不是窗口——持有旧快照不受后续运行影响。计量经 Bus 订阅 `UsageEvent` 累积（Disposable 登记进 effect 栈，shutdown 自动退订）；治理器的全部"钱账"最终都能对上。

## 五、设计底线：治理是组件，不是内核机制

值得注意的反面：治理**不在**引擎里。`Governor` 端口留在 context 包、引擎对它零依赖——门面（组合根）在回合前对历史调用 `enforce` 并回写。为什么？因为引擎只有一个，而治理策略会有很多种；把某一种治理焊进循环，等于替所有用户预定了偏见。内核是语法不是管家（docs/02 原则 1）——这条底线让"换一种治理策略"永远只是换一个组件。

## 与 M1 验收的对应

这套机制的验收不是主观的：`packages/context/evals/` 里躺着评测集运行器——3–5 段真实对话日志 × 预算档位，只认本文的三条硬指标（预算达标、must-survive 保留、卸载往返）。欢迎用你自己的真实日志跑一遍：`uv run python packages/context/evals/run_evals.py`。
