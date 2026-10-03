# Tutelary

> **Tutelary** /ˈtjuːtələri/，"护法的"——像护法神守着修行者一样，守着 Agent 的预算、权限、隔离与记忆。

**可拆解的 Agent 基础设施**：每个能力——上下文治理、记忆、沙箱、权限、LLM 适配、Agent 循环——都是独立可装、独立可用、独立发布的包；一个只做装配的薄内核把它们缝起来。别把整个框架买回家，按需取用。

## 为什么

主流 Agent 框架都在解决"怎么编排"，把**运行时治理**（上下文预算、权限门、执行隔离）完全留给你 DIY；而记忆/沙箱产品各自要求你"整体买进场"。Tutelary 占中间的位置：

- **上下文治理组件（旗舰）**：预算声明、压缩、卸载、token 内省——确定性运行时工程，可测试可复现；
- **契约中立层**：`Memory` / `Sandbox` 等窄端口 + 随包契约测试——任何符合契约的实现可互换，内置实现无特权；
- **中立基准**：接契约的实现一键跑分（[对比报告](benchmarks/memory/REPORT.md)）。

## 安装

```bash
pip install tutelary          # 整船：Agent 门面 + 全部组件
pip install tutelary-context  # 单点取用：只要上下文治理
```

## 快速开始

### 单点：上下文治理（不经引擎，接进你自己的循环）

```python
import asyncio

from tutelary.context import Budget, ContextGovernor
from tutelary.core.types import Message, TextBlock


async def main() -> None:
    provider = MyProvider()  # 任何实现 Provider 端口的对象（摘要经它生成）
    governor = ContextGovernor(provider, MyBus(), config=Budget(total=8000))

    result = await governor.enforce(
        history_messages,
        keep_substrings=["必须保留：回滚预案定在周五窗口执行"],  # 钉住不压缩
    )
    print(governor.report().render())  # token 瀑布：这次运行的钱花在哪了


asyncio.run(main())
```

压缩后的内省瀑布（`examples/only-context.py` 的真实输出）：

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

两条机器可判的硬指标：压缩后实测 token ≤ 预算声明；`keep_substrings` 标注的 must-survive 内容全部保留——做不到就抛类型化错误，绝不静默丢数据。

### 整船：Agent 门面

```python
from tutelary import Agent

agent = Agent.from_config(
    {
        "provider": {
            "type": "openai-compatible",
            "base_url": "https://your-gateway/v1",
            "api_key": "...",
            "model": "your-model",
        },
        "memory": {"type": "markdown", "root": "./agent-memory"},
        "policy": {"allow": ["run_command", "read_file"]},
    }
)

async for event in agent.run("帮我跑一下构建"):
    print(type(event).__name__)  # 事件溯源：每个动作都是事件
```

策略返回 `Suspend` 时循环安全停驻，审批后 `resume` 从断点续跑；命令经沙箱执行（默认断网）；`TurnCommitted` 经 Bus 落进记忆。

## 组件一览

| 发行包 | 导入 | 职责 |
|---|---|---|
| `tutelary-core` | `tutelary.core` | 契约内核：类型词汇、事件与 Bus、五端口、effect 栈、装配器。零依赖、零 IO |
| `tutelary-context` ⭐ | `tutelary.context` | 上下文治理：预算、压缩、卸载、token 内省 |
| `tutelary-memory` | `tutelary.memory` | Markdown 后端的记忆实现（写路径走事件） |
| `tutelary-policy` | `tutelary.policy` | 可组合权限策略 + Suspend 审批判定 |
| `tutelary-sandbox` | `tutelary.sandbox` | Subprocess / Docker 执行隔离，默认断网 |
| `tutelary-providers` | `tutelary.providers` | OpenAI 兼容 / Anthropic 流式适配 + 重试与故障转移 |
| `tutelary-engine` | `tutelary.engine` | 事件溯源 Agent 循环 + Suspend 断点续跑 |
| `tutelary` | `tutelary.runtime` | 伞包：`Agent` 门面 + 预设装配（组合根） |
| `tutelary-mem0-adapter` | `tutelary_mem0_adapter` | 官方 Mem0 适配（第三方形态的生态示例） |

每个组件只依赖 core，组件之间零横向依赖——这条红线由 CI 的架构门禁强制；**每个包在独立 venv 里只装自身 + core 跑通自己的测试**，隔离安装矩阵是"à la carte"承诺的机器证明。

## 文档

- [设计文档地图](docs/README.md)：定位 → 哲学 → 内核 → 契约 → 仓库形态 → 开发计划
- [deep-dive：上下文预算治理是怎么做的](docs/deep-dive/context-budget.md)
- [memory 基准对比报告](benchmarks/memory/REPORT.md)
- 单点示例：[examples/](examples/)（每个组件一份 `only-*.py`，全离线可跑）+ [整船示例](examples/full-agent/run.py)

## 状态

设计基线定稿，M0–M4 完成（内核、旗舰、组件三连、整船双裁判、基准与 Mem0 adapter）；M5 发布就绪进行中。v2 展望：多 Agent 编排、trace/回放、MCP、skills。详见[开发计划](docs/09-development-plan.md)。

## 协议

Apache-2.0。见 [LICENSE](LICENSE) 与 [CONTRIBUTING](CONTRIBUTING.md)。
