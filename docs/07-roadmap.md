# 07 · 路线图与发布策略

状态：基线（2026-10-01）。

## 1. 里程碑

### M0 · 内核（tutelary-core）

- 四要素实现：types / events（Bus 两语义）/ ports / lifecycle（effect 栈）/ assembler；
- 架构测试 6 条（[05 §4](05-repository.md)）+ 契约测试插件骨架；
- **验收**：core 零依赖证明（import 白名单测试绿）；Assembler 四种 fail-fast 错误各有单测；装配中途失败回滚有单测。

### M1 · 旗舰（tutelary-context）

- 预算声明、压缩、卸载、token 内省（"这次运行 token 花在哪了"）；
- `examples/only-context.py`；
- **验收**：only-context 用 fake LLM 跑通；隔离安装测试绿；压缩策略在真实对话日志上完成调参（自用验证，不发布），质量以固定评测集的硬指标判定（见 [09](09-development-plan.md) M1）。

### M2 · 组件三连（memory / sandbox / policy）

- memory：MarkdownProvider 内置实现 + memory 契约检查项就绪；
- sandbox：DockerRuntime（docker 为可选依赖，惰性导入）+ SubprocessRuntime；
- policy：Allowlist / PathSandbox / ApprovalGate 可组合策略 + Suspend 挂起/恢复协议；
- **验收**：三包 only-\* 全绿；tutelary-memory 通过自家契约套件。

### M3 · 整船（providers / engine / runtime 伞包）

- providers：OpenAI / Anthropic 兼容协议流式解析 + 重试/限流/故障转移；
- engine：事件溯源异步生成器循环（消费五端口 + Suspend 断点续跑）；
- runtime：`Agent` 门面 + 预设装配（config → 组件映射，组合根的唯一归属）；
- **验收（双裁判，两关都过抽象才算成立）**：
  1. 整船——`examples/full-agent` 不改 core/组件一行代码跑通；
  2. 单点——全部 `examples/only-*.py` 跑通。

### M4 · 立中立

- 基准套件 v0：memory workload，接契约的实现一键跑分、结果可复现；
- 官方 Mem0 adapter（借力 + 证明契约中立）；
- **验收**：内置实现与 Mem0 adapter 在同一基准上产出对比报告。

### M5 · 公开发布（v1 首发）

- 占位清单执行（GitHub org、PyPI 八包、域名——占位可提前，发布在此）；
- PyPI 逐包首发，顺序沿用组件叙事：core + context → memory / sandbox / policy / providers → engine + 伞包；
- 社区门面七件齐备；
- 发布三件套：README 演示（token 瀑布图）、deep-dive 首篇《上下文预算治理是怎么做的》、基准对比报告随发；
- **验收**：PyPI 全部可安装且隔离安装矩阵绿；demo 与文档支撑"看懂并装上"。

### v2 展望（不承诺日期，逐个立 ADR）

orchestration（多 Agent 编排）、observe（trace/回放查看器）、MCP、skills、评测 harness。

## 2. 发布纪律

- M5 之前不公开发布——全部组件过 only-\* 与双裁判之后才首发；
- 公开发布的**最终时点由项目所有者决定**：里程碑只负责把项目带到“随时可发”的就绪态，发布本身是独立的显式决定，不排期、不自动触发；
- 版本 lockstep（[ADR-0003](decisions/0003-lockstep-versioning.md)），tag 驱动全量发布；
- 每次公开发布三件套：README 更新、CHANGELOG、至少一篇 deep-dive 文档。

## 3. 占位清单（立即执行，成本≈0）

- [ ] GitHub org：`tutelary`
- [ ] PyPI：`tutelary`、`tutelary-core`、`tutelary-context`、`tutelary-memory`、`tutelary-sandbox`、`tutelary-policy`、`tutelary-providers`、`tutelary-engine`
- [ ] 域名：tutelary.dev（备选 .io）
- [ ] 其他平台同名 ID（X / Reddit / HN 用名）

## 4. 节奏原则

**深度优先于广度**：任何时刻只允许一个"进行中"组件；每个组件发布前必须有 real-workload 依据——旗舰 context 必须压在真实工作流上调参，不许只对着自写测试跑（对着想象需求做设计 = 把自己的偏见学一遍）。
