# Changelog

Tutelary 全部发行包共享同一版本号（lockstep，见 [ADR-0003](docs/decisions/0003-lockstep-versioning.md)）：端口签名变更 = major；事件/端口新增 = minor；实现内部变更 = patch。发布由项目所有者决定时点（见 docs/09 M5）。

## 0.1.0（未发布——发布就绪态）

首个公开版本。设计基线（01–07 + ADR×3）定稿后，按里程碑推进的全部能力：

### tutelary-core

- 词汇表：消息/工具/调用/记忆/执行/权限判定的 frozen dataclass 全集；
- 事件协议：15 个基线事件 + 双语义总线（observe 扇出隔离 / intercept 拦截链可改写否决）；
- 五端口签名（Provider / Tool / Policy / Memory / Sandbox）+ Executor；
- 生命周期原语：Component（鸭子装配）、Disposable、effect 栈（LIFO 回滚、失败聚合、取消放行）；
- 装配器：缺端口 / 重复提供 / 循环依赖 / 配置校验四种 fail-fast 错误 + 装配中途失败回滚；
- 随契约发布的零依赖假实现：FakeBus / FakeProvider / FakeMemory / FakeSandbox；
- 契约测试插件：`--tutelary-contract=<port>` 经入口点组发现套件，内置实现与第三方同套。

### tutelary-context（旗舰）

- 预算声明（总预算 + 五段份额，构造期校验）；
- 唯一压缩策略 SummarizeFoldStrategy：最老优先折叠，摘要经 Provider 端口生成；keep_substrings 钉住使"must-survive 全保留"机器可判；
- 卸载仓库：大工具结果移出上下文、按引用取回；
- token 内省瀑布（实测/预算/压缩节省/卸载节省/LLM 计量）；
- 可判定验收：评测集运行器 + 两条硬指标（预算达标、must-survive 保留）。

### tutelary-memory / tutelary-policy / tutelary-sandbox

- memory：Markdown 文件后端，事件写路径（TurnCommitted 幂等落盘）+ 子串召回；过自家契约套件；
- policy：AllOf / AnyOf 组合子、Allowlist、PathSandbox（防路径逃逸）、ApprovalGate（Suspend 判定侧）；
- sandbox：SubprocessRuntime（超时击杀）+ DockerRuntime（惰性导入、默认断网）；docker-marked 独立测试车道。

### tutelary-providers

- OpenAI 兼容与 Anthropic 两个流式适配（SSE → 内核事件，工具调用聚合）；
- ResilientProvider：重试 + 故障转移 + 并发上限（只在首事件前重试，不重复输出）。

### tutelary-engine / tutelary（伞包）

- 事件溯源异步生成器循环：召回注入、策略判定、工具执行回喂、Suspend 断点续跑；
- Agent 门面：组合根唯一归属，治理接线与 Bus 桥接；from_config 预设装配；沙箱化 ExecTool。

### 工程与治理

- 架构门禁 6 条（AST import 图）+ 九包隔离安装矩阵；
- memory 基准 v0 + 官方 Mem0 adapter（第三方形态）+ 对比报告框架；
- CI：lint / 测试 / 类型检查 / docker-marked 独立车道。

### FlowCoder 对齐（F1，进行中）

- 引擎生命周期 Hooks：8 个生命周期点（session_start / turn_start / pre_send /
  post_receive / pre_tool_use / post_tool_use / turn_end / session_end），声明式
  Hook 支持 reject（先于策略阻断）与 prompt 注入；HookEvent 回执可观测，异常隔离；
- 运行预算：token / 轮次 / 时间 / 成本四维，触顶"收敛不击杀"——注入收敛消息、
  摘除工具 schema，BudgetBreached 事件可观测；预算跨 Suspend/续跑连续。
