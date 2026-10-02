"""only-policy：不依赖引擎，单独使用 policy 组件（M2 验收裁判）。

演示可组合策略：AllOf 把 Allowlist + PathSandbox + ApprovalGate 叠成
一道门，对四类调用给出 Allow / Deny / Suspend 三种判定——纯离线、
无 IO、check 可重复。
跑法：``uv run python examples/only-policy.py``
"""

from tutelary.core import ToolCall
from tutelary.policy import AllOf, Allowlist, ApprovalGate, PathSandbox


def main() -> None:
    gate = AllOf(
        Allowlist(("read_file", "run_cmd", "web_search")),
        PathSandbox(("./workspace",)),
        ApprovalGate(tools=("run_cmd",)),
    )

    calls = [
        (
            "工作区内读文件",
            ToolCall(id="c1", name="read_file", arguments={"path": "./workspace/notes.md"}),
        ),
        ("名单外工具", ToolCall(id="c2", name="install_package")),
        (
            "逃逸路径",
            ToolCall(id="c3", name="read_file", arguments={"path": "./workspace/../../etc/passwd"}),
        ),
        (
            "需要审批的命令",
            ToolCall(id="c4", name="run_cmd", arguments={"path": "./workspace/build.sh"}),
        ),
    ]
    for label, call in calls:
        decision = gate.check(call)
        kind = type(decision).__name__
        detail = getattr(decision, "reason", "") or getattr(decision, "prompt", "")
        print(f"[{kind:<7}] {label}" + (f" —— {detail}" if detail else ""))

    kinds = {type(gate.check(call)).__name__ for _, call in calls}
    assert kinds == {"Allow", "Deny", "Suspend"}
    print("组合判定 OK：Allow / Deny / Suspend 三态齐全")


if __name__ == "__main__":
    main()
