# 06 · 扩展指南：写一个 Memory2

状态：基线（2026-10-01）。面向第三方组件作者；以记忆为例，Sandbox/Provider 同理。

## 0. 前提

你的实现只依赖 `tutelary-core`（端口与类型词汇），不 import 任何 `tutelary.<兄弟>` 包。

Protocol 是结构化类型：**你的类不需要继承任何基类，长得符合端口即可**；想进整船装配，再按 §2 声明 `Component` 协议。

发布形态：发布**你自己的顶层包**（如 `memory2`），只声明依赖 `tutelary-core`；不要发布进 `tutelary.*` 命名空间——它单方所有（`langchain-openai` 不叫 `langchain.*` 是同一个道理）。

## 1. 最小路径：实现端口

```python
# memory2/__init__.py —— 只 import tutelary.core
from tutelary.core.ports import Memory
from tutelary.core.types import MemoryHit, MemoryScope

class Memory2:
    async def recall(self, query: str, scope: MemoryScope) -> list[MemoryHit]:
        ...

    async def load_context(self, query: str, scope: MemoryScope) -> str:
        ...
```

单点取用即刻可用（最常见的接入形态）：

```python
from tutelary.context import ContextGovernor, Budget

gov = ContextGovernor(budget=Budget(history=30_000), llm=call_llm, memory=Memory2())
```

## 2. 装配路径：Component 协议（可选）

要进整船、被 Assembler 统一管理生命周期，声明 provides/requires 并实现 setup：

```python
from typing import Any, ClassVar
from tutelary.core.lifecycle import Component, Disposable
from tutelary.core.ports import Memory, Bus
from tutelary.core.events import TurnCommitted

class Memory2(Component):
    name = "memory2"
    provides = Memory
    requires = (Bus,)                       # 写路径：订阅事件
    config_model = Memory2Config            # 鸭子类型：有 model_validate(dict) 即可（pydantic 兼容）

    def __init__(self, bus: Bus, config: Memory2Config) -> None:
        # 装配器按 requires 声明顺序注入；config 以关键字注入
        self._bus, self._cfg = bus, config

    def setup(self) -> Disposable:
        # 注册即挂 effect 栈：整船 shutdown 或装配失败时自动退订
        return self._bus.observe(TurnCommitted, self._on_turn)
```

用户侧：

```python
tut = await Assembler().use(Memory2, config={"dsn": "postgres://..."}).use(Engine).assemble()
```

## 3. 机器验证：跑契约套件

```bash
pip install "tutelary-core[contract]"
pytest --tutelary-contract=memory --memory-factory=memory2.tests.make_memory
```

全绿 = 兼容承诺成立。套件固定检查清单见 [04 §4](04-contracts.md)。

## 4. 写路径语义

记忆的写入统一走事件：实现方订阅 `TurnCommitted`，不占用端口方法——机制统一（一切经 Bus），端口保持窄读路径。契约要求幂等消费（事件可能重放）。

## 5. 端口不合适怎么办

**第二实现是端口的裁判。** 如果你的实现被迫扭曲以适配端口，这不是你的问题——提 issue，端口该改。

流程：ADR 论证 → lockstep 大版本 → 契约套件同步更新 → 内置实现同步迁移。

前期端口保持"宁窄勿宽"：加方法向后兼容（minor），收窄语义才是破坏（major）。
