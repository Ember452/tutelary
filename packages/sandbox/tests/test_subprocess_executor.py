"""SubprocessExecutor：执行、编码容错、超时击杀、关闭后拒绝复用。"""

import sys

import pytest

from tutelary.core.types import ExecSpec
from tutelary.sandbox._subprocess import SubprocessExecutor
from tutelary.sandbox.errors import SandboxError


def _spec(code: str, timeout: float | None = 30.0) -> ExecSpec:
    return ExecSpec(command=(sys.executable, "-c", code), timeout_seconds=timeout)


async def test_run_captures_stdout_and_exit_code():
    result = await SubprocessExecutor().run(_spec("print('hello')"))
    assert result.exit_code == 0
    assert result.stdout.strip() == "hello"
    assert result.timed_out is False


async def test_stderr_is_captured():
    result = await SubprocessExecutor().run(_spec("import sys; sys.stderr.write('坏消息')"))
    assert "坏消息" in result.stderr


async def test_nonzero_exit_is_a_result_not_an_error():
    result = await SubprocessExecutor().run(_spec("raise SystemExit(3)"))
    assert result.exit_code == 3


async def test_timeout_kills_the_process():
    result = await SubprocessExecutor().run(_spec("import time; time.sleep(30)", timeout=0.5))
    assert result.timed_out is True


async def test_missing_command_returns_typed_result():
    result = await SubprocessExecutor().run(
        ExecSpec(command=("definitely-not-a-real-binary-xyz",), timeout_seconds=5.0)
    )
    assert result.exit_code is None
    assert "command not found" in result.stderr


async def test_env_variables_are_injected():
    result = await SubprocessExecutor().run(
        ExecSpec(
            command=(sys.executable, "-c", "import os; print(os.environ.get('TUTELARY_PROBE'))"),
            timeout_seconds=30.0,
            env={"TUTELARY_PROBE": "seen"},
        )
    )
    assert result.stdout.strip() == "seen"


async def test_reuse_after_aclose_raises():
    executor = SubprocessExecutor()
    await executor.aclose()
    await executor.aclose()  # 幂等
    with pytest.raises(SandboxError, match="不能复用"):
        await executor.run(_spec("pass"))
