"""SubprocessRuntime：acquire 校验与端口语义（执行在 Executor 上）。"""

import sys

import pytest

from tutelary.core.types import ExecSpec
from tutelary.sandbox.errors import SandboxSpecError
from tutelary.sandbox.subprocess_runtime import SubprocessRuntime


async def test_empty_command_raises_spec_error():
    runtime = SubprocessRuntime()
    with pytest.raises(SandboxSpecError, match="不能为空"):
        await runtime.acquire(ExecSpec(command=()))


async def test_acquire_returns_a_working_executor():
    runtime = SubprocessRuntime()
    executor = await runtime.acquire(
        ExecSpec(command=(sys.executable, "-c", "print('ok')"), timeout_seconds=30.0)
    )
    result = await executor.run(
        ExecSpec(command=(sys.executable, "-c", "print('ok')"), timeout_seconds=30.0)
    )
    assert result.exit_code == 0
    assert result.stdout.strip() == "ok"
