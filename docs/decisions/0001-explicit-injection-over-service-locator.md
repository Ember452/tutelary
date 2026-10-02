# ADR-0001 · 显式构造注入，而不是 cordis 式服务定位器

状态：已接受（2026-10-01）

## 背景

cordis 的空间可组合性由 Context Proxy + 服务注册表实现：`ctx.timer.timeout(...)` 按属性名运行时查找服务，未声明 `inject` 就访问会在运行时报错。这让插件代码极简，但依赖两样东西：JS Proxy 的拦截能力，以及"运行时才发现错误"的容忍度。

## 决定

Tutelary 采用**显式声明 + 构造注入**：

- 依赖以 `requires: ClassVar` 类型声明，装配期解析；
- 装配器按声明顺序构造注入（`__init__(self, memory: Memory, ...)`），组件内部永远不做查找；
- 错误全部前移到装配期：`MissingPortError` / `DuplicatePortError` / `CircularRequirementError`；
- `Tutelary.get(Port)` 类型化访问仅限组合根与测试；组件内禁止持有整船句柄。

## 理由

1. Python 类型文化：pyright 严格模式 + Protocol 优先。service locator 是运行时才炸的字符串查找，与"fail fast"原则直接冲突；
2. 端口实例经构造函数进入组件，pyright 可全程跟踪类型——cordis 的 ctx 魔法在 Python 做不到等价物；
3. 响应式热装卸（服务下线自动卸载消费者）对回合制 Agent 无真实需求；放弃它换来零 Proxy 复杂度。

## 后果

组件代码比 cordis 略啰嗦（显式声明 + 构造函数）；换来：装配错误 100% 前移、全链路可静态分析、内核不需要 Proxy/描述符黑魔法。

## 重评触发

出现真实的"运行中服务可用性动态变化"需求（长驻服务 + 插件热插拔）时立新 ADR；在此之前本决定不做重评。
