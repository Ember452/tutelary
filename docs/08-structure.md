# 08 · 项目结构

状态：工作草案 v0（2026-10-01）。目录级结构的权威定义，不精确到文件；结构变化直接修订本文。

## 1. 仓库顶层

```
tutelary/                      # GitHub 仓库 = uv workspace 根
├── README.md                  # 项目门面：一句话定位、快速开始、文档入口
├── LICENSE                    # Apache-2.0（生态型库的通行选择，含专利授权条款）
├── CHANGELOG.md               # lockstep 单文件变更日志
├── CONTRIBUTING.md            # 贡献流程：环境搭建、测试义务、提交规范
├── SECURITY.md                # 安全问题报告通道（安全是本项目卖点，此文件不是装饰）
├── CODE_OF_CONDUCT.md
├── pyproject.toml             # workspace 声明 + 根级开发工具配置（ruff / pytest / 覆盖率）
├── .pre-commit-config.yaml    # ruff check + format 钩子
├── packages/                  # 全部发行包：一目录一 wheel（见 §2）
├── examples/                  # 单点取用示例 + 整船示例（见 §5）
├── docs/                      # 本文档集（地图见 README）
├── tests/
│   ├── architecture/          # 跨包边界门禁：AST import 图 + 6 条规则（见 05 §4）
│   ├── isolation/             # 隔离安装测试的矩阵定义（见 05 §5）
├── benchmarks/                # 基准套件（见 07 M4）：接契约的实现一键跑分
└── .github/
    ├── workflows/             # test.yml（测试+门禁）/ publish.yml（tag 驱动全量发布）
    ├── ISSUE_TEMPLATE/        # bug / feature / component-proposal
    └── PULL_REQUEST_TEMPLATE.md
```

社区门面（README / LICENSE / CHANGELOG / CONTRIBUTING / SECURITY / CODE_OF_CONDUCT / Issue·PR 模板）是大型开源项目的标准配置，**M5 首发前齐备**（账号/包名占位可在 M0 就做，内容随发布齐备）。协议选 **Apache-2.0**：库要下游敢依赖，Apache 与 MIT 都是通行解，Apache 额外带专利授权；AGPL（annona 的选择）是应用防白嫖的思路，库不这么选。

规则：**单元测试住在各包内**（`packages/<pkg>/tests/`，隔离安装时随包跑）；只有跨包的架构门禁与隔离矩阵放仓库顶层。

## 2. packages/ —— 一目录一发行包

| 目录 | PyPI 发行名 | 导入包 | 职责 | 依赖 |
|---|---|---|---|---|
| `packages/core` | tutelary-core | tutelary.core | 契约内核：类型词汇、事件与 Bus、五端口、Component/effect 栈、Assembler、随包发布的 Fake 实现 | 无（仅标准库） |
| `packages/providers` | tutelary-providers | tutelary.providers | LLM 多协议流式适配 + 重试/限流/故障转移（Provider 端口实现） | core |
| `packages/context` | tutelary-context | tutelary.context | ⭐ 旗舰：上下文治理——预算声明、压缩、卸载、token 内省 | core |
| `packages/memory` | tutelary-memory | tutelary.memory | 记忆 Hub、内置 provider、召回（Memory 端口实现） | core |
| `packages/sandbox` | tutelary-sandbox | tutelary.sandbox | 执行隔离：DockerRuntime / SubprocessRuntime（Sandbox 端口实现） | core |
| `packages/policy` | tutelary-policy | tutelary.policy | 可组合权限策略 + 审批挂起/恢复（Policy 端口实现） | core |
| `packages/engine` | tutelary-engine | tutelary.engine | 参考循环：事件溯源异步生成器，消费五端口（组装者之一） | core |
| `packages/runtime` | tutelary | tutelary.runtime | 伞包：`Agent` 门面、预设装配、对全部子包的依赖声明（组装者之二） | 全部子包 |

每个包内固定三件套：

```
packages/<pkg>/
├── pyproject.toml             # 发行名 / 依赖声明（core 恒为空）
├── src/tutelary/<pkg>/        # 实现代码
└── tests/                     # 包内单测
```

**Fake 随契约发布**（借鉴 annona-spi 的 `spi/fake/`）：core 附带零依赖假实现（FakeProvider / FakeMemory / FakeSandbox / FakeBus），与契约同版本发布。三个作用：① 各组件包与下游用户的测试不依赖真实 LLM / Docker；② only-\* 示例的"不联网"由标准 fake 供给，不再各写各的；③ 第三方实现有行为基线可对照。

**第三方形态的官方 adapter**：`tutelary-mem0-adapter`（导入名 `tutelary_mem0_adapter`）按 [01 §5](01-positioning.md) 的生态形态发布在 packages/ 内——mem0ai 为可选 extra、惰性导入。它不在上表八组件之列，是"第二实现检验"的常驻示例（docs/07 M4）。

包内布局刻意**不做** annona 式统一分层模板（controller/service/repository 那套）：Python 包粒度小，模板是 Java 大模块的产物；边界由架构测试管，不由目录模板管。

注意：engine 虽然消费五端口，但**只依赖 core**——它 import 的是端口协议，兄弟组件的实现是装配时注入的，不是编译期依赖。

## 3. 依赖方向（唯一规则）

```
runtime(伞包) ──► { context, memory, sandbox, policy, providers, engine } ──► core
                     （组件之间零横向）
```

- 所有组件包 → core；组件之间零横向依赖；engine 与 runtime 是仅有的组装者；
- 跨组件协作只有两条通道：Bus 事件、端口注入（规则细节见 [05 §3](05-repository.md)）；
- 新增组件 = 新增 `packages/<pkg>` 目录 + §2 表格加一行 + PyPI 占名（流程见 [07](07-roadmap.md)）；
- 守门分工（借鉴 annona 的两层哲学）：编译期能强制的（workspace 成员、依赖声明）放 pyproject；import 边界放架构测试；不为每个边界新造机制。

## 4. 安装后的运行时结构（PEP 420 命名空间）

用户 `pip install` 之后，site-packages 里出现的是：

```
site-packages/
└── tutelary/                  # 命名空间包：无 __init__.py，多个 wheel 共同填充
    ├── core/                  # ← 来自 tutelary-core
    ├── context/               # ← 来自 tutelary-context
    ├── memory/                # ← 来自 tutelary-memory
    ├── runtime/               # ← 来自 tutelary（伞包）
    └── ...
```

- 任何发行包都不得携带 `tutelary/__init__.py`；
- 只装 `tutelary-context` 时，磁盘上只有 `tutelary/core` + `tutelary/context`——这就是"单点取用"在磁盘上的样子；
- 装伞包 `tutelary` 时，全部子目录到齐——这就是"整船"。

`tutelary.*` 命名空间**单方所有**（同 `google.*` / `azure.*` 规则）：第三方组件发布自己的顶层包、只依赖 `tutelary-core`（先例：`langchain-openai` 之于 langchain），不发布进 `tutelary.*`。

## 5. examples/

```
examples/
├── only-*.py                  # 单点取用示例：一组件一份，不经引擎单独跑通（验收裁判之一）
└── full-agent/                # 整船示例：runtime 门面的完整用法（验收裁判之二）
```

## 6. docs/

```
docs/
├── README.md                  # 文档地图与阅读顺序
├── 01–07                      # 定位 / 哲学 / 内核 / 契约 / 仓库 / 扩展 / 路线图
├── 08-structure.md            # 本文
└── decisions/                 # ADR：关键取舍的 Why 与重评条件
```
