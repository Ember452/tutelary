"""only-sandbox：不依赖引擎，单独使用 sandbox 组件（M2 验收裁判）。

演示三件事：SubprocessRuntime 执行与结果回传、超时击杀、DockerRuntime
在无 docker 环境下的优雅降级。子进程只跑当前解释器，全程离线。
跑法：``uv run python examples/only-sandbox.py``
"""

import asyncio
import sys

from tutelary.core.types import ExecSpec
from tutelary.sandbox import SandboxUnavailableError, SubprocessRuntime
from tutelary.sandbox.docker_runtime import DockerRuntime


async def main() -> None:
    runtime = SubprocessRuntime()
    spec = ExecSpec(
        command=(sys.executable, "-c", "print('inside subprocess')"), timeout_seconds=30.0
    )
    executor = await runtime.acquire(spec)
    result = await executor.run(spec)
    print("子进程输出：", result.stdout.strip())
    assert result.exit_code == 0 and not result.timed_out

    slow = await executor.run(
        ExecSpec(command=(sys.executable, "-c", "import time; time.sleep(30)"), timeout_seconds=1.0)
    )
    print(f"超时击杀 OK：timed_out={slow.timed_out}")
    assert slow.timed_out is True
    await executor.aclose()

    docker = DockerRuntime()
    try:
        docker_executor = await docker.acquire(ExecSpec(command=("echo", "hi")))
    except SandboxUnavailableError as exc:
        print("Docker 不可用（类型化降级，不崩溃）：", exc)
    else:
        print("Docker 守护进程可用——容器冒烟见 docker-marked 车道（-m docker）")
        await docker_executor.aclose()


if __name__ == "__main__":
    asyncio.run(main())
