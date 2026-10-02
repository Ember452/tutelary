# 05 · 仓库形态与发布工程

状态：基线（2026-10-01）。决策依据见 [ADR-0002](decisions/0002-monorepo-workspace.md) / [ADR-0003](decisions/0003-lockstep-versioning.md)。

## 1. 结构：单仓多包（uv workspace）

> 目录级结构的权威定义在 [08 项目结构](08-structure.md)；本节树是发布工程视角的速览，两处不一致时以 08 为准。

```
tutelary/                              # GitHub 仓库 = uv workspace 根
├── pyproject.toml                     # [tool.uv.workspace] members = ["packages/*"]
├── packages/
│   ├── core/        → PyPI tutelary-core      → import tutelary.core
│   ├── providers/   → tutelary-providers      → tutelary.providers
│   ├── context/     → tutelary-context        → tutelary.context        ⭐ 旗舰
│   ├── memory/      → tutelary-memory         → tutelary.memory
│   ├── sandbox/     → tutelary-sandbox        → tutelary.sandbox
│   ├── policy/      → tutelary-policy         → tutelary.policy
│   ├── engine/      → tutelary-engine         → tutelary.engine
│   └── runtime/     → tutelary (伞包)         → tutelary.runtime        # 整船门面
├── examples/
│   ├── only-context.py / only-memory.py / only-sandbox.py / only-policy.py
│   └── full-agent/
├── docs/                              # 本目录
├── tests/
│   ├── architecture/                  # 边界门禁（§4）
│   └── isolation/                     # 隔离安装（§5）
└── .github/workflows/                 # test.yml / publish.yml
```

## 2. 命名空间规则（PEP 420 原生命名空间）

- 每个发行包 shipping `src/tutelary/<sub>/`；**任何包都不得放 `tutelary/__init__.py`**；
- 伞包发行名 `tutelary`，内容只有 `tutelary/runtime/`（整船门面）+ 对全部子包的依赖声明；
- wheel 名与导入名映射固定：`tutelary-<sub>` ↔ `tutelary.<sub>`；
- 成员包模板（core 示例）：

```toml
[project]
name = "tutelary-core"
dependencies = []                      # 永远为空

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/tutelary"]
```

## 3. 依赖方向（唯一规则）

**所有组件包 → core；组件之间零横向依赖；engine 与 runtime 是仅有的组装者。**
跨组件协作只有两条通道：Bus 事件、端口注入。

```
runtime(伞包) ──► { context, memory, sandbox, policy, providers, engine } ──► core
                     （组件之间零横向）
```

## 4. 架构测试（CI 门禁，不靠自觉）

`tests/architecture/` 下 6 条 pytest（AST import 图）：

1. `test_core_zero_dependencies`——core 的 import ⊆ 标准库 ∪ tutelary（唯一例外：`contract.py` 可 import pytest——随包发布的契约插件，pytest 属 `[contract]` extra，不进运行时依赖）；
2. `test_no_horizontal_imports`——组件包只准 import core 与自身子模块；
3. `test_umbrella_direction`——任何子包禁止 import `tutelary.runtime`（伞包只进不出）；
4. `test_lazy_heavy_imports`——docker/grpc/torch 等重依赖禁止出现在模块顶层（函数体内合法）；
5. `test_no_domain_vocabulary`——core 源码禁止出现具体产品/场景词；
6. `test_only_examples_smoke`——`examples/only-*.py` 全部纳入 CI 冒烟（fake LLM，不联网）。

## 5. 隔离安装测试（à la carte 的机器证明）

CI matrix：对每个组件包，建独立 venv，**只安装该包 + tutelary-core + pytest**，跑该包测试。任何"顺手 import 了兄弟包"或"顶层拖进重依赖"都会在这里爆红。

此 job 的存在本身写进 README 作为卖点——它是"每个组件独立可装"的机器证明，几乎没有项目做这个。

## 6. 版本与发布

- **lockstep**：全部发行包共享同一版本号（依据 [ADR-0003](decisions/0003-lockstep-versioning.md)）；
- tag `vX.Y.Z` → `publish.yml` 逐包构建、发布全部 wheel；
- CHANGELOG 单文件，按版本分节；
- 版本语义：端口签名变更 = major；事件/端口新增 = minor；实现内部变更 = patch。
