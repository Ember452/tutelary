# 04 · 组件契约与事件协议

状态：工作草案 v0（2026-10-01）。M5 公开发布前，签名与事件清单随实现直接修订、直接改本文，无需 ADR；发布后本文才成为兼容承诺，改动走 ADR + lockstep 版本语义（§5）。

## 1. 组件接入五义务

每个组件（内置或第三方）准入必须满足：

1. **只依赖 core**：import 白名单 = 标准库 ∪ `tutelary.core`（架构测试强制）；
2. **独立入口 API**：不经引擎、不经装配器即可使用——写得出 `examples/only-<组件>.py`；
3. **依赖以 Protocol 参数声明**：不横向 import 兄弟组件；
4. **重依赖惰性导入**：docker/grpc 等可选依赖只允许出现在函数体内；
5. **过契约测试套件**：内置与第三方实现跑同一套（见 §4）。

"写不出 only-\* 示例的模块 = 耦合没切干净"——这是抽象正确性的第二裁判。

## 2. 五端口行为契约

方法签名见 [03 §4](03-kernel.md)，本节是实现方必须遵守/禁止的行为承诺：

| 端口 | 实现方必须 | 实现方禁止 |
|---|---|---|
| Provider | 事件顺序跟随 LLM 原始序（Thinking/Stream/ToolUse）；Usage 必发；放行 `CancelledError` | 吞掉取消；自作主张重试（重试/限流属于本包内 client 层职责，不属于端口语义） |
| Tool | `spec` 与 schema 一致；execute 声明副作用是否幂等；超时自守 | 越过 Policy 直接执行；在 execute 里改权限判定 |
| Policy | `check` 无副作用（可重复调用）；`Suspend` 携带可展示给用户的 prompt | 在 check 里做 IO |
| Memory | recall 无命中返回 `[]` 不抛错；写路径订阅 `TurnCommitted` 且幂等消费 | 读路径阻塞事件循环；把大对象塞进 `MemoryHit` |
| Sandbox | acquire 失败抛类型化错误；Executor 关闭时回收全部资源；**默认断网**，开放网络须显式 | 在 acquire 里执行用户代码 |

## 3. 事件协议（15 个基线事件）

| 事件 | 时机 | 关键字段 |
|---|---|---|
| `TurnStarted` | 回合开始 | session_id, input |
| `ThinkingText` | 思维增量 | delta |
| `StreamText` | 文本增量 | delta |
| `ToolUseEvent` | 发起工具调用 | call |
| `ToolResultEvent` | 工具返回 | call, result |
| `PermissionRequest` | 需要判定 | call |
| `PermissionResponse` | 判定完成 | call, decision |
| `RetryEvent` | 将要重试 | attempt, reason |
| `UsageEvent` | 计量 | usage |
| `CompactStarted` | 压缩开始 | reason, tokens_before |
| `CompactNotification` | 压缩完成 | summary, tokens_after |
| `TurnComplete` | 回合结束 | turn_id, usage |
| `TurnCommitted` | 回合内容落定（记忆写路径的统一消费点） | turn_id, text, session_id |
| `LoopComplete` | 运行结束 | session_id |
| `ErrorEvent` | 错误 | error, phase |

规则：事件 frozen；新增事件走 ADR（minor）；组件不得假设别人订阅了什么；`intercept` 链只允许用于 SPI 类事件，流式增量（StreamText/ThinkingText）不设拦截。`TurnCommitted` 是 M0 实现期补入的——Memory 写路径契约依赖它，基线清单原本漏了它。

## 4. 契约测试套件（中立性的机器证明）

随 core 发布：`pip install "tutelary-core[contract]"`，pytest 插件入口：

```bash
pytest --tutelary-contract=memory --tutelary-factory=my_pkg.tests.make_memory
```

以 memory 为例，套件固定检查：

1. 种子内容后，同 scope 下 `recall` 命中；
2. `load_context` 返回内容包含种子内容；
3. 订阅 Bus 后派发 `TurnCommitted`，内容落库；重复派发，幂等；
4. 无命中返回 `[]`，不抛错；
5. `shutdown()` 后资源归零；重复调用幂等；
6. 错误路径抛类型化错误，不抛裸 `Exception`。

**内置实现跑的是同一套件（CI 强制）**——这是"一切实现无特权"的执行机制，也是第三方作者的质量反馈环。

## 5. 端口演进规则（M5 公开发布后生效）

发布前的签名是工作草案：实现逼着改就改，同步改本文即可，不需要 ADR。

发布后：

- 端口保持"宁窄勿宽"：加方法是向后兼容（minor），收窄语义才是破坏（major）；
- 任何签名变更：ADR 论证 → lockstep 大版本 → 契约套件同步更新 → 内置实现同步迁移；
- "第二实现是端口的裁判"：端口被真实第二实现逼改版，属于流程正常工作，不视为设计失败。
