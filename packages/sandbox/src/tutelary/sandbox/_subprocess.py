"""SubprocessExecutor：本地子进程执行器——每次 run 起一个进程，超时击杀。"""

from __future__ import annotations

import asyncio
import os

from tutelary.core.types import ExecResult, ExecSpec
from tutelary.sandbox.errors import SandboxError

DEFAULT_TIMEOUT_SECONDS = 60.0
"""spec 未声明超时时沙箱自守的兜底值（docs/04 §2"超时自守"）。"""


def _decode(raw: bytes | None) -> str:
    return (raw or b"").decode("utf-8", errors="replace")


class SubprocessExecutor:
    """acquire 发放的句柄：run 执行、aclose 归还；关闭后不可复用。

    每次 run 起一个全新进程；超时未退出即 kill（超时本身是结果的一部分，
    记入 ExecResult.timed_out）。子进程继承宿主环境并叠加 spec.env——
    这样 PATH 等基本变量不丢，声明变量可注入。
    """

    def __init__(self) -> None:
        self._closed = False

    async def run(self, spec: ExecSpec) -> ExecResult:
        if self._closed:
            raise SandboxError("executor 已关闭，不能复用——重新 acquire 领取")
        timeout = (
            spec.timeout_seconds if spec.timeout_seconds is not None else DEFAULT_TIMEOUT_SECONDS
        )
        try:
            process = await asyncio.create_subprocess_exec(
                *spec.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=spec.cwd,
                env={**os.environ, **spec.env} if spec.env else None,
            )
        except FileNotFoundError:
            return ExecResult(exit_code=None, stderr=f"command not found: {spec.command[0]!r}")
        except OSError as exc:
            return ExecResult(exit_code=None, stderr=f"spawn failed: {exc}")

        timed_out = False
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except TimeoutError:
            process.kill()
            stdout, stderr = await process.communicate()
            timed_out = True

        return ExecResult(
            exit_code=process.returncode,
            stdout=_decode(stdout),
            stderr=_decode(stderr),
            timed_out=timed_out,
        )

    async def aclose(self) -> None:
        """归还执行器；幂等，之后不可再 run。"""
        self._closed = True
