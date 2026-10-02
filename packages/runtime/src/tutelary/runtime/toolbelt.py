"""整船内置件：工具带与沙箱化命令工具（组合根组装，引擎按 Tool 端口消费）。"""

from __future__ import annotations

from collections.abc import Sequence

from tutelary.core.ports import Sandbox, Tool
from tutelary.core.types import ExecSpec, ToolCall, ToolResult, ToolSpec


class Toolbelt:
    """把 N 个 Tool 聚合成引擎要的形状：specs() 声明 + execute() 按名路由。"""

    def __init__(self, tools: Sequence[Tool] = ()) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools:
            self._tools[tool.spec.name] = tool

    def specs(self) -> tuple[ToolSpec, ...]:
        return tuple(tool.spec for tool in self._tools.values())

    async def execute(self, call: ToolCall) -> ToolResult:
        tool = self._tools.get(call.name)
        if tool is None:
            return ToolResult(call_id=call.id, output=f"未知工具：{call.name}", is_error=True)
        return await tool.execute(call)


class ExecTool:
    """命令执行工具：经 Sandbox 端口领取执行器跑命令，用毕归还。

    默认断网（ExecSpec.network=False，docs/04 §2）；超时自守可配。
    """

    def __init__(
        self,
        sandbox: Sandbox,
        *,
        name: str = "run_command",
        description: str = "在沙箱里执行一条命令并返回输出",
        timeout_seconds: float = 60.0,
    ) -> None:
        self._sandbox = sandbox
        self._name = name
        self._description = description
        self._timeout = timeout_seconds

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self._name,
            description=self._description,
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要执行的命令及其参数",
                    }
                },
                "required": ["command"],
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        raw = call.arguments.get("command")
        if not isinstance(raw, list) or not raw:
            return ToolResult(
                call_id=call.id, output="参数 command 必须是非空字符串数组", is_error=True
            )
        command = tuple(str(part) for part in raw)
        spec = ExecSpec(command=command, timeout_seconds=self._timeout)
        executor = await self._sandbox.acquire(spec)
        try:
            result = await executor.run(spec)
        finally:
            await executor.aclose()
        output = f"超时被击杀（>{self._timeout:g}s）" if result.timed_out else result.stdout
        if result.stderr:
            output = f"{output}\n[stderr] {result.stderr}".strip()
        failed = result.exit_code != 0 or result.timed_out
        return ToolResult(call_id=call.id, output=output.strip() or "(无输出)", is_error=failed)
