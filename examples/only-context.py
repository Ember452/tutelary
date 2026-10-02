"""only-context：不依赖引擎，单独使用 context 组件（M1 验收裁判）。

演示四件事：预算声明、超预算自动压缩（摘要走 fake LLM）、大工具结果
卸载与取回、token 内省瀑布——全程离线。
跑法：``uv run python examples/only-context.py``
"""

import asyncio

from tutelary.context import Budget, ContextGovernor
from tutelary.core import (
    FakeBus,
    FakeProvider,
    Message,
    StreamText,
    TextBlock,
    ToolResult,
    ToolResultBlock,
    Usage,
    UsageEvent,
)


def _turn(index: int) -> Message:
    role = "user" if index % 2 == 0 else "assistant"
    filler = "细节。" * 150
    return Message(
        role=role, content=(TextBlock(text=f"第 {index} 轮：讨论部署窗口与预算口径。{filler}"),)
    )


async def main() -> None:
    provider = FakeProvider(
        [
            StreamText(delta="摘要：前期多轮围绕部署窗口与回滚预案展开，关键决定是周五窗口上线。"),
            UsageEvent(usage=Usage(input_tokens=5200, output_tokens=60)),
        ]
    )
    governor = ContextGovernor(
        provider,
        FakeBus(),
        config=Budget(total=8000, system=0.10, history=0.60, tools=0.10, memory=0.10, reserve=0.10),
    )

    must_survive = "必须保留：回滚预案定在周五窗口执行"
    messages: list[Message] = [
        Message(role="system", content=(TextBlock(text="你是部署助手。"),)),
        Message(role="user", content=(TextBlock(text=f"早会记录：{must_survive}"),)),
        *(_turn(i) for i in range(40)),
        Message(
            role="assistant",
            content=(
                ToolResultBlock(result=ToolResult(call_id="call-logs", output="日志行 " * 3000)),
            ),
        ),
    ]

    result = await governor.enforce(messages, keep_substrings=[must_survive])
    print(f"压缩执行：{result.compacted}；卸载 {result.offloaded} 块工具结果")
    print(governor.report().render())

    recovered = governor.offload_store.get("call-logs")
    assert recovered.startswith("日志行")
    print("卸载取回 OK：", recovered[:12], "…")

    flat = "\n".join(
        block.text for m in result.messages for block in m.content if isinstance(block, TextBlock)
    )
    assert must_survive in flat
    print("must-survive 保留 OK")


if __name__ == "__main__":
    asyncio.run(main())
