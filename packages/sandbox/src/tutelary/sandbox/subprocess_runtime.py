"""SubprocessRuntime：本地子进程沙箱——诚实声明它不提供网络隔离。"""

from __future__ import annotations

from tutelary.core.lifecycle import Component
from tutelary.core.ports import Executor, Sandbox
from tutelary.core.types import ExecSpec
from tutelary.sandbox._subprocess import SubprocessExecutor
from tutelary.sandbox.errors import SandboxSpecError


class SubprocessRuntime(Component):
    """轻量执行隔离：进程边界 + 超时击杀。

    ``ExecSpec.network`` 对子进程没有强制力——真断网靠 DockerRuntime
    （容器默认 ``--network none``，见 docs/plans/2026-10-02-m2-tasks.md
    §2 的诚实声明）。平台纪律（09 M2）：Windows 走 Proactor 循环、
    Linux 走默认循环，测试双平台都跑；路径行为按宿主 OS。
    """

    name = "sandbox-subprocess"
    provides = (Sandbox,)
    requires = ()

    async def acquire(self, spec: ExecSpec) -> Executor:
        """按规格领取执行器；只做校验，不在这里执行用户代码（docs/04 §2）。"""
        if not spec.command:
            raise SandboxSpecError("ExecSpec.command 不能为空")
        return SubprocessExecutor()
