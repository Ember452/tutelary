"""FakeSandbox：领取→执行→归还流程与用后不可复用。"""

import pytest

from tutelary.core.errors import TutelaryError
from tutelary.core.fakes import FakeExecutor, FakeSandbox
from tutelary.core.types import ExecResult, ExecSpec


async def test_acquire_run_returns_canned_result_and_records_spec():
    sandbox = FakeSandbox()
    executor = await sandbox.acquire(ExecSpec(command=("echo", "hi")))
    assert isinstance(executor, FakeExecutor)
    result = await executor.run(ExecSpec(command=("echo", "hi")))
    assert result == ExecResult(exit_code=0, stdout="fake-exec")
    assert len(sandbox.specs) == 1
    assert executor.calls[0].command == ("echo", "hi")


async def test_executor_rejects_reuse_after_aclose():
    sandbox = FakeSandbox()
    executor = await sandbox.acquire(ExecSpec(command=("echo",)))
    await executor.aclose()
    with pytest.raises(TutelaryError):
        await executor.run(ExecSpec(command=("echo",)))


async def test_executor_replays_scripted_results():
    executor = FakeExecutor(results=[ExecResult(exit_code=2, stderr="no")])
    result = await executor.run(ExecSpec(command=("false",)))
    assert result.exit_code == 2
    assert result.stderr == "no"
