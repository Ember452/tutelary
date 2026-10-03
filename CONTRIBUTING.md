# 贡献指南

谢谢你考虑为 Tutelary 出力。这个项目的价值主张是"可拆解 + 契约中立"——贡献流程的一切安排都为了守住它。

## 环境搭建

```bash
git clone https://github.com/Ember452/tutelary.git
cd tutelary
uv sync --all-packages      # Python 3.13，uv workspace；.python-version 钉主版本
uv run pytest -q            # 全部测试（含架构门禁与隔离安装矩阵）
uv run ruff check .
uv run ruff format --check .
uv run pyright
```

依赖只进所属包的 `pyproject.toml`（`uv add --package tutelary-<sub> <dep>`）。**`packages/core` 永远零第三方依赖**——没有例外。

## 先读设计，再动代码

- [docs/02-philosophy.md](docs/02-philosophy.md)：可组合性从哪来、拒绝什么；
- [docs/03-kernel.md](docs/03-kernel.md) / [docs/04-contracts.md](docs/04-contracts.md)：内核形状与端口契约（M5 首发前是工作草案：实现逼着改就改，同任务更新文档）；
- [docs/08-structure.md](docs/08-structure.md)：目录结构权威定义；
- [AGENTS.md](AGENTS.md)：AI 协作与质量约束（对人类贡献者同样适用）。

## 不可协商的红线

1. **永不关闭裁判**：`tests/architecture`、契约测试套件、`examples/only-*`、隔离安装矩阵是项目的设计裁决。某个裁判挡住了你，那是设计信号——停下来讨论，而不是 skip/xfail/删测试。
2. **依赖方向**：组件只依赖 core、组件之间零横向依赖、core 零外部依赖。跨组件协作只有两条路：Bus 事件、端口注入。
3. **类型化边界**：公开 API 全类型注解、pyright 干净；跨包数据是 frozen dataclass，不是裸 dict。
4. **每个组件写得出 `only-*` 示例**：不经引擎单独跑通——写不出就是耦合没切干净。
5. **异步纪律**：事件循环内不阻塞（文件 IO 走 `to_thread`）、IO 必有超时、永不吞 `CancelledError`。

## 提交规范

- 提交信息英文，一行主题 + 空行 + 正文说清 what 与 why；
- 新行为带测试，bug 修复带回归测试；
- 文档与实现同任务更新（03/04/08 随实现修订，09 记录阶段状态）。

## 第三方组件

发布你自己的顶层包、只依赖 `tutelary-core`（`langchain-openai` 之于 langchain 的形态）；`tutelary.*` 命名空间单方所有。跑通 `--tutelary-contract=<port>` 契约套件即可宣称兼容——参考 [tutelary-mem0-adapter](packages/mem0_adapter/) 这个官方第三方形态示例与 [扩展指南](docs/06-extending.md)。

## 行为准则

见 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。安全问题走 [SECURITY.md](SECURITY.md) 的私密通道，不要开公开 issue。
