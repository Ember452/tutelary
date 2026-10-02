"""真实容器冒烟（docker-marked 车道）：默认排除，本机/CI 用 -m docker 运行。"""

import pytest

from tutelary.core.types import ExecSpec
from tutelary.sandbox.docker_runtime import DockerRuntime

pytestmark = pytest.mark.docker


async def test_echo_runs_inside_a_container():
    runtime = DockerRuntime()
    executor = await runtime.acquire(ExecSpec(command=("python", "-c", "print('in-container')")))
    result = await executor.run(
        ExecSpec(command=("python", "-c", "print('in-container')"), timeout_seconds=120.0)
    )
    assert result.exit_code == 0
    assert "in-container" in result.stdout
    await executor.aclose()
