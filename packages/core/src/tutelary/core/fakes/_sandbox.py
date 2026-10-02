"""FakeSandbox：Sandbox 端口的假实现——不真正执行，离线验证领取/执行/归还流程。"""

from __future__ import annotations

from collections.abc import Sequence

from tutelary.core.errors import TutelaryError
from tutelary.core.ports import Executor
from tutelary.core.types import ExecResult, ExecSpec


class FakeExecutor:
    """记录收到的 ExecSpec 并回放预设 ExecResult；aclose 后不可复用。"""

    def __init__(self, results: Sequence[ExecResult] | None = None) -> None:
        self.calls: list[ExecSpec] = []
        self._results = list(results) if results is not None else None
        self._closed = False

    async def run(self, spec: ExecSpec) -> ExecResult:
        if self._closed:
            raise TutelaryError("FakeExecutor 已关闭，不能复用——重新 acquire 领取")
        self.calls.append(spec)
        if self._results:
            return self._results.pop(0)
        return ExecResult(exit_code=0, stdout="fake-exec")

    async def aclose(self) -> None:
        self._closed = True


class FakeSandbox:
    """acquire 每次发放全新 FakeExecutor；不执行任何真实命令。"""

    def __init__(self) -> None:
        self.executors: list[FakeExecutor] = []
        self.specs: list[ExecSpec] = []

    async def acquire(self, spec: ExecSpec) -> Executor:
        self.specs.append(spec)
        executor = FakeExecutor()
        self.executors.append(executor)
        return executor
