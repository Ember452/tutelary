# FlowCoder 对齐改造主计划（2026-10-02）

状态：活文档——改造主控。背景与事实依据见会话勘探（FlowCoder `docs/plans/FRAMEWORK_REACTOR_PLAN.md`、`agent/core.py`、`hooks/`、`permissions/`、`security/`、`context/`、`scripts/chaos.py`）；所有者决定：**不考虑复杂度，学最好的**，机制级采纳、架构不动（Tutelary 的内核/装配器/Bus 保持）。

## 0. 关键事实（诚实底账）

- FlowCoder **自己也拒绝了**微内核/服务定位器（FRAMEWORK_REFACTOR_PLAN《为什么不做微内核容器》）——两家在编排哲学上本就一致：显式注入 + 工厂组合根。
- **Keel 框架抽象在 FlowCoder 里只活了一天即被回滚**（`4128c40`）；准入五义务与双裁判以**政策文档**形态存活。Tutelary 是 Keel 计划预期中的"真实外部项目验收消费者"（其 dogfooding 条款）——F6 在 docs/02 血统表补记此事。
- 真正被生产验证的是：`agent/core.py` 的循环分相、`hooks/`、`permissions/` 六层门、`security/taint.py`、`context/` 双层管理、`agent/budget.py`、`scripts/chaos.py`。

## 1. 采纳清单（F1–F6 分期）

| 期 | 机制 | FlowCoder 出处 | Tutelary 落点 | 验收 |
|---|---|---|---|---|
| F1 | 生命周期 Hooks（8 事件、reject、prompt 注入、once） | `hooks/engine.py` 等 | engine 包 `hooks.py`（可选协作者，非端口——FlowCoder 同款） | hook 单测镜像其测试意图；reject 阻断执行；prompt 注入进 system |
| F1 | 四维预算"收敛不击杀"（token/轮次/时间/成本） | `agent/budget.py` | engine 包 `budget.py`（`RunBudget`，与 context 的窗口 Budget 区分） | 预算耗尽 → 注入收敛消息 + 摘工具 schema + `BudgetBreached` 事件，回合自然收敛 |
| F2 | 工具执行升级：ToolSpec 增 category / is_concurrency_safe；只读并行批、写串行 | `tools/base.py`、`agent/tool_execution.py` | core types（04 §5 minor）+ engine | 读写交错正确性测试 |
| F2 | 注入防御：TaintState + 工具结果安检（污染期 allow→ask 只升不降） | `security/taint.py`、`gate.py` | policy 包 + engine 挂点（docs/03 预告的"安检"） | 污染升级路径测试 |
| F3 | 权限门分层：DangerousCommandDetector、yaml 规则、模式矩阵——组合子预置配方 | `permissions/` 5 文件 | policy 包 | 镜像 `test_tool_authorization` 意图 |
| F4 | 双层上下文：OffloadStore 落盘化（预览标签可回读）、auto-compact 触发器 + 断路器防抖 | `context/manager.py` 等 | context 包 | 落盘回读往返 + 防抖测试 |
| F5 | MemoryHub 扇出（超时隔离）+ 子代理 AgentTool（fork 子引擎 + 工具过滤） | `memory/providers/hub.py`、`tools/agent/` | memory 包 / runtime 包 | 扇出超时测试；子代理 run_to_completion 测试 |
| F6 | 混沌演练（llm-outage / budget-exceeded / rate-limit-storm）+ docs/02 血统表诚实补记 | `scripts/chaos.py` | tests/ 集成车道 | 三场景注入全过 |

语义级细则一并采纳：审批超时 = deny（时长可配）、ALLOW_ALWAYS 合成规则、记忆提取隔轮回后台执行。

## 2. 明确不采纳（记录理由）

- **future 式审批握手**：保留事件溯源状态机——基础设施库需要可持久化挂起；future 是连接绑定的，断线即失。
- **双层事件协议**（StreamEvent / AgentEvent 两套词表）：Tutelary 的 LLMEvent / Event 已有软分层。
- **服务定位器 / 容器 / HMR**：FlowCoder 自己也拒绝了。
- **ToolSearch 延迟发现、watchdog、teams/worktree**：非编排主干，v2 backlog。

## 3. 端口与文档义务

- 核心事件新增：`HookEvent`、`BudgetBreached`（04 §3 表同步，15 → 17）。
- `ToolSpec` 增字段（F2，04 §5 工作草案 minor）。
- 每期收尾：03/04/08 随实现修订、`tests/architecture` 与 only-\* 全绿、隔离矩阵绿。

## 4. 里程碑状态

- [x] F1 hooks + 四维预算收敛（2026-10-02 完成）
  - 质量评判：HookEngine/RunBudget 各自独立模块、可选协作者不进端口（FlowCoder 同款）；
    `_drive` 按 FlowCoder 分相流水展开，相序自释；预算状态挂会话使 Suspend/续跑连续。
    评测中修掉两处自伤：post_receive 每请求触发曾被测试预期漏算；Hook 异常原被静默
    吞掉（补 HookOutcome.errors 转可观测回执）；同步 _turn_close 属设计错误（改异步生成器）。
- [x] F2 工具执行升级 + 注入防御（2026-10-02 完成）
  - 质量评判：工具相拆成判定/执行/结果三段，事件序确定而执行延迟重叠；
    HookOutcome.errors 让 Hook 异常可观测；taint 三件套共享单实例由组合根
    接线（FlowCoder factory 注释同款）。评测修掉：门禁 2 命名空间误伤第三方
    形态顶层名；门面缺 resume 的真实缺口（taint 停驻流需要）。
- [ ] F3 权限门分层
- [ ] F4 双层上下文
- [ ] F5 MemoryHub + 子代理
- [ ] F6 混沌演练 + 血统补记
