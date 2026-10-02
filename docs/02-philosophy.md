# 02 · 设计哲学

状态：基线（2026-10-01）。

## 1. 两条可组合性（血统：cordis）

Tutelary 的内核哲学来自 cordis（cordiverse/cordis）明确表述的元框架目标——"时空可组合性"（A Meta-Framework of Spatiotemporal Composability）：

- **时间可组合（temporal）**：组件被移除时，其全部副作用被完全回滚。实现是统一的 effect 栈：事件订阅、子任务、连接、定时器全部登记在栈上，卸载即 LIFO 逆序回收。
- **空间可组合（spatial）**：组件间的依赖必须显式声明，由运行时在装配期解析；缺依赖、循环依赖在启动瞬间报错，而不是运行中途爆炸。

这两条合起来才叫"可独立发布、独立使用"：只做声明式依赖没有回滚保证，组件会漏资源；只做 effect 回滚没有依赖声明，组件仍然拆不出来。

## 2. 血统表：从哪里来，改了什么

| 设计点 | 来源 | Tutelary 的 Python 化 |
|---|---|---|
| effect/LIFO 卸载（时间可组合） | cordis `Fiber.effect` | `AsyncExitStack` 语义显式化为 effect 栈（[03 §5](03-kernel.md)） |
| 声明式依赖（空间可组合） | cordis `inject` + 服务注册表 | 弃 Proxy 服务定位器，改为 `provides/requires` + fail-fast 装配器（[ADR-0001](decisions/0001-explicit-injection-over-service-locator.md)） |
| 事件即 SPI（框架扩展点也是事件） | cordis `internal/*` 事件 | 类型化事件的 `intercept` 链（[04 §3](04-contracts.md)） |
| 配置声明与校验 | cordis Standard Schema | 鸭子类型 config 协议，兼容 pydantic 但零依赖（[03 §5](03-kernel.md)） |
| 每组件窄端口 | flow-agent `ports.py` | 原样：每端口 2–3 个方法 |
| 显式依赖注入对象 | akashic `AgentLoopDeps` | 原样：构造注入，不藏字符串查找 |
| emit/observe 双语义总线 | akashic `EventBus` | 收敛为 observe（扇出隔离）/ intercept（拦截链）（[04 §3](04-contracts.md)） |
| 依赖方向做成 CI 测试 | flow-agent import graph | 原样并加强（[05 §4](05-repository.md)） |
| 治理机制基线（14 事件词汇、Suspend 挂起/续跑协议、准入五义务、整船+单点双裁判） | FlowCoder/Keel 的已验证实践 | 去领域化移植——机制继承，产品与场景词汇零继承 |
| 契约测试套件 | anyio / fsspec 模式 | 随 core 发布；第三方实现与内置实现跑同一套（[04 §4](04-contracts.md)） |

## 3. 明确不采纳清单

| cordis 机制 | 不采纳理由 |
|---|---|
| Proxy 式 `ctx.foo` 服务定位 | Python 类型文化（pyright 严格、Protocol 优先）与之冲突；运行时字符串查找把装配错误推迟到运行中 |
| TS interface merging 的静态服务类型 | Python 无类型合并；端口注入天然类型安全 |
| 深入模块加载器的 HMR | Agent 运行是短生命周期回合制，重启换配置即可；Python 的 importlib 对类/单例状态的热替换脆弱 |
| 五种事件派发全搬 | 只保留 observe/intercept 两种语义（YAGNI），需要时经 ADR 增加 |
| 每包独立版本 + peerDependencies | npm 的生态强制力（单版本去重 + peer 语义）Python 没有；见 [ADR-0003](decisions/0003-lockstep-versioning.md) |
| 响应式热装卸（服务下线自动卸载消费者） | 回合制运行用不上；声明式 + fail-fast 已覆盖真实需求 |

## 4. 设计原则四条

1. **内核是语法，不是管家**：`tutelary-core` 零依赖、零 IO、零运行时调度；只提供词汇表（类型/事件/端口）、生命周期原语、装配器和事件总线。被 ≥2 个组件共享的才进内核，只被一个组件用的留在组件内。
2. **一切实现无特权**：内置实现（tutelary-memory 等）与第三方实现走同一条端口、同一套契约测试。内置实现 = 第一个第三方实现。
3. **fail fast**：缺端口、重复提供、循环依赖、配置校验失败，全部在装配期报出；运行时不做任何字符串查找。
4. **卸载即回滚**：任何组件登记的资源都在 effect 栈上；拿掉组件、装配中途失败、整船 shutdown，全部 LIFO 完全回滚。
