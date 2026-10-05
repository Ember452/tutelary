"""跨组件边界的词汇表（docs/03 §2）。

全部是 frozen dataclass：字段具名、实例不可变、可安全跨包传递。
端口签名禁止裸 ``dict[str, Any]``（AGENTS §4.3）；仅有的两处
``Mapping`` 字段——JSON Schema 与工具实参——是天然开放的结构，
语义是"模式/透传"，不是按键消费的数据负载。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal

type Role = Literal["system", "user", "assistant", "tool"]

type ToolCategory = Literal["read", "write", "command"]
"""工具的副作用分类：read 只读、write 改写、command 执行命令。"""

EMPTY_MAPPING: Mapping[str, Any] = MappingProxyType({})


# ---------------------------------------------------------------------------
# 消息与内容块
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class TextBlock:
    """纯文本内容块。"""

    text: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ThinkingBlock:
    """思维内容块（推理模型的思考产物）。"""

    text: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolUseBlock:
    """消息内的工具调用块。"""

    call: ToolCall


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolResultBlock:
    """消息内的工具结果块。"""

    result: ToolResult


type ContentBlock = TextBlock | ThinkingBlock | ToolUseBlock | ToolResultBlock


@dataclass(frozen=True, slots=True, kw_only=True)
class Message:
    """一条对话消息；content 是内容块序列，顺序即语义顺序。"""

    role: Role
    content: tuple[ContentBlock, ...] = ()


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolSpec:
    """工具的声明式规格；parameters 是该工具实参的 JSON Schema。

    category 与 is_concurrency_safe 供引擎编排执行（多调用单轮时的并行
    批次划分）：并发安全的工具可并行执行，其余串行；默认串行（保守）。
    """

    name: str
    description: str = ""
    parameters: Mapping[str, Any] = EMPTY_MAPPING
    category: ToolCategory = "read"
    is_concurrency_safe: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolCall:
    """一次工具调用请求；arguments 是提供方透传的开放 JSON 实参。"""

    id: str
    name: str
    arguments: Mapping[str, Any] = EMPTY_MAPPING


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolResult:
    """一次工具执行的产出；is_error 为真时 output 是错误说明。"""

    call_id: str
    output: str
    is_error: bool = False


# ---------------------------------------------------------------------------
# 调用与计量
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class LLMRequest:
    """一次 LLM 调用的全部输入。"""

    model: str
    messages: tuple[Message, ...]
    tools: tuple[ToolSpec, ...] = ()
    max_output_tokens: int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class Usage:
    """一次调用的 token 计量。"""

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


# ---------------------------------------------------------------------------
# 记忆
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class MemoryScope:
    """记忆寻址范围：agent 全局，可选收敛到单个会话。"""

    agent_id: str
    session_id: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class MemoryHit:
    """一条召回结果；score 的量纲由提供方自洽，契约不比较（docs/04 §2）。"""

    id: str
    text: str
    score: float = 0.0


# ---------------------------------------------------------------------------
# 执行
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecSpec:
    """一次隔离执行的规格；network 默认关闭，开放须显式（docs/04 §2）。"""

    command: tuple[str, ...]
    timeout_seconds: float | None = None
    network: bool = False
    cwd: str | None = None
    env: Mapping[str, str] = EMPTY_MAPPING


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecResult:
    """一次隔离执行的产出；exit_code 为 None 表示进程被信号终止或未产生退出码。"""

    exit_code: int | None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False


# ---------------------------------------------------------------------------
# 权限判定
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class Allow:
    """放行。"""


@dataclass(frozen=True, slots=True, kw_only=True)
class Deny:
    """拒绝；reason 面向用户可展示。"""

    reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class Suspend:
    """挂起等待审批；prompt 面向用户可展示（docs/04 §2）。"""

    prompt: str


type Decision = Allow | Deny | Suspend
