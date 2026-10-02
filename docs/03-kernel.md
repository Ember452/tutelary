# 03 · 内核设计（tutelary-core）

状态：工作草案 v0（2026-10-01）。M5 公开发布前：签名只是当前最好的想法，实现逼着改就改，直接修订本文；发布后：改动才走 ADR + 版本语义（见 [04 §5](04-contracts.md)）。

## 0. 硬承诺

- **零第三方依赖**：core 的 import 仅允许标准库与 tutelary 自身（CI 强制）。pydantic 模型兼容 config 协议但不被依赖——`pip install tutelary-core` 拉不进任何东西。
- **零 IO、零调度**：core 不发请求、不开线程、不管理事件循环；它是词汇表 + 规则。

## 1. 五个文件总览

```
tutelary/core/
├── types.py        # ① 词汇表：跨边界类型原语
├── events.py       # ② 事件协议与总线
├── ports.py        # ③ 五端口签名
├── lifecycle.py    # ④ 生命周期原语：Component / Disposable / effect 栈
├── assembler.py    # ⑤ 装配器（fail-fast 解析）
├── errors.py       # ⑥ 类型化错误（M0 实现期增补，被 ①–⑤ 共同引用）
├── contract.py     # 契约测试插件骨架（[contract] extra，见 04 §4）
└── fakes/          # 随契约发布的假实现（见 08 §2）
```

①–③ 是"词"，④–⑤ 是"法"。

## 2. ① 词汇表（types.py）

跨组件边界一律用这些类型，禁止裸 dict：

- 消息与内容块：`Message` / `ThinkingBlock` / `ToolUseBlock` / `ToolResultBlock`
- 工具：`ToolCall` / `ToolSpec` / `ToolResult`
- 调用与计量：`LLMRequest` / `Usage`
- 记忆：`MemoryScope` / `MemoryHit`
- 执行：`ExecSpec` / `ExecResult`
- 权限：`Decision`（= `Allow | Deny(reason) | Suspend(prompt)`）

建模规则：core 内用 frozen dataclass（保持零依赖）；字段全部具名；端口签名里禁止出现 `dict[str, Any]`。

## 3. ② 事件协议与总线（events.py）

事件基类 `Event`（frozen dataclass）。v1 事件清单 14 个，见 [04 §3](04-contracts.md)。

总线只有两个订阅动词、一个发射动词：

```python
class Bus(Protocol):
    def observe[E: Event](self, et: type[E], handler: Handler[E]) -> Disposable:
        """消费者订阅：异步扇出，单个 handler 失败被隔离、不传染（UI/日志/记忆写路径）。"""

    def intercept[E: Event](self, et: type[E], handler: Handler[E]) -> Disposable:
        """SPI 订阅：拦截链，可返回新事件替换、返回 None 否决（策略注入、框架行为扩展）。"""

    async def emit[E: Event](self, event: E) -> E:
        """先跑 intercept 链（可改写/否决），再扇出 observe。"""
```

- 监听器注册返回 `Disposable`，自动挂 effect 栈——组件卸载即退订；
- `Bus` 本身是一个端口（`provides = Bus`）：组件要订阅事件就 `requires = (Bus,)`，没有特权通道。

## 4. ③ 五端口（ports.py，基线签名）

```python
class Provider(Protocol):
    """LLM 调用：请求进，流式事件出。"""
    def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]: ...

class Tool(Protocol):
    """工具：声明式规格 + 执行。"""
    @property
    def spec(self) -> ToolSpec: ...
    async def execute(self, call: ToolCall) -> ToolResult: ...

class Policy(Protocol):
    """权限判定：可组合；Suspend 触发审批挂起/恢复协议。"""
    def check(self, call: ToolCall) -> Decision: ...

class Memory(Protocol):
    """记忆读路径。写路径统一走事件：实现方 requires Bus 并订阅 TurnCommitted。"""
    async def recall(self, query: str, scope: MemoryScope) -> list[MemoryHit]: ...
    async def load_context(self, query: str, scope: MemoryScope) -> str: ...

class Sandbox(Protocol):
    """执行隔离：按规格领取执行器，用毕归还。"""
    async def acquire(self, spec: ExecSpec) -> Executor: ...
    # Executor: run(spec) -> ExecResult，且实现 aclose()
```

设计决定：

- `Memory` 读路径只有两个方法；写路径不进端口，统一由实现方订阅 `TurnCommitted`——机制统一（一切经 Bus），端口保持窄，契约测试可验证消费行为。
- `Decision.Suspend` 是一等公民：判定为挂起时循环安全停驻、审批后从断点续跑。治理是卖点，端口必须能表达它。
- 五端口是主导抽象不是全集：引擎的真实协作方（lifecycle hooks、注入提示、工具结果安检、子 Agent 委派）在 M3 引擎实现时经 ADR 增长为 8–10 个窄接口是预期产出，不构成设计失败。

## 5. ④ 生命周期原语（lifecycle.py）

```python
class Component:
    name: ClassVar[str]                          # 必填：装配日志与错误定位用
    provides: ClassVar[PortSpec] = ()            # 提供的端口类型
    requires: ClassVar[PortSpec] = ()            # 依赖的端口类型（要订阅事件就 require Bus）
    config_model: ClassVar[type | None] = None   # 鸭子类型：有 model_validate(dict) 即可（pydantic 兼容）

    def __init__(self, *deps: Any, config: Any = None) -> None:
        """装配器按 requires 声明顺序位置注入端口实例；config 以关键字注入。"""

    def setup(self) -> Disposable | None:
        """副作用登记：订阅、连接、启动后台任务。返回清理函数（挂 effect 栈）或 None。"""
```

组件**不必继承** `Component`：装配器按类属性鸭子读取 `provides` / `requires` / `config_model`，无 `setup` 视为无副作用——端口实现可以直接声明成组件（M0 实现期确认）。

`Disposable` = `Callable[[], Awaitable[None]]` 或实现 `aclose()` 的对象。

effect 栈语义（时间可组合的落点）：

1. 组件 `setup()` 的返回值、组件内 `bus.observe/intercept` 的返回值，全部入栈；
2. `shutdown()` 或装配中途失败时，**LIFO 逆序执行**全部清理函数（支持异步）；
3. 装配失败同样回滚已成功 setup 的组件——失败的装配不留半拉子状态。

## 6. ⑤ 装配器（assembler.py）

```python
tut = await (
    Assembler()
    .use(Memory2, config={"dsn": "postgres://..."})
    .use(ContextGovernor)     # requires: (Provider,)
    .use(Engine)              # requires: (Provider, Memory, Policy)
    .assemble()
)
...
await tut.shutdown()
```

装配算法（顺序固定）：

1. 收集全部 `use()` 的 provides/requires，建端口供需图；
2. 校验，任一失败立即抛错：缺端口 → `MissingPortError`；同一端口多个提供者 → `DuplicatePortError`；requires 图有环 → `CircularRequirementError`；config 过不了 `config_model.model_validate` → `ConfigValidationError`；
3. 按拓扑序实例化组件，构造注入；
4. 依序调 `setup()`，返回值入 effect 栈；任一步失败 → 回滚已 setup 的组件后再抛错。

结果对象 `Tutelary` 提供 `get(Port)` 类型化访问——**仅限组合根与测试使用**，组件内部禁止持有整船句柄（见 [ADR-0001](decisions/0001-explicit-injection-over-service-locator.md)）。

## 7. 非目标（内核永远不做）

运行时插拔/热装卸、字符串服务查找、任务调度、任何 IO、任何业务词汇（产品名、场景策略）。
