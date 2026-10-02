"""PathSandbox：路径约束——声明的参数键必须落在允许根目录内。"""

from __future__ import annotations

from pathlib import Path

from tutelary.core.types import Allow, Decision, Deny, ToolCall

DEFAULT_PATH_KEYS = ("path", "file", "file_path", "filepath")
"""默认检查的参数键：声明式约定，可用 argument_keys 覆盖。"""


class PathSandbox:
    """文件路径沙箱：防绝对路径与 ``..`` 逃逸。

    判定规则：call 的参数里出现任一声明键时，把值 resolve 后校验是否
    落在某个允许根之内；不涉及路径参数的调用不受影响。相对路径按当前
    工作目录解析——组合根应使用绝对路径根（在模块层说明，不做运行时
    猜测）。check 无副作用（docs/04 §2）。
    """

    def __init__(
        self,
        roots: tuple[str | Path, ...],
        argument_keys: tuple[str, ...] = DEFAULT_PATH_KEYS,
    ) -> None:
        self._roots = [Path(root).resolve() for root in roots]
        self._keys = frozenset(argument_keys)

    def check(self, call: ToolCall) -> Decision:
        for key in self._keys:
            if key not in call.arguments:
                continue
            candidate = Path(str(call.arguments[key])).resolve()
            if not self._under_any_root(candidate):
                return Deny(reason=f"路径 {call.arguments[key]!r} 逃逸出允许根目录")
        return Allow()

    def _under_any_root(self, candidate: Path) -> bool:
        return any(candidate == root or root in candidate.parents for root in self._roots)
