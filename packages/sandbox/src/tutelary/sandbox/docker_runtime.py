"""DockerRuntime：容器沙箱——默认断网，docker SDK 惰性导入。

M2 的刻意简化（随真实使用修订，见 docs/plans/2026-10-02-m2-tasks.md）：
stdout/stderr 合并取回；非零退出码从容器异常里尽力提取；超时交给
SDK 的 HTTP 读超时参数。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from tutelary.core.lifecycle import Component
from tutelary.core.ports import Executor, Sandbox
from tutelary.core.types import ExecResult, ExecSpec
from tutelary.sandbox.errors import SandboxError, SandboxSpecError, SandboxUnavailableError


@dataclass(frozen=True, slots=True)
class DockerConfig:
    """容器配置：镜像与工作目录。"""

    image: str = "python:3.13-slim"
    workdir: str = "/workspace"

    @classmethod
    def model_validate(cls, data: dict[str, object]) -> DockerConfig:
        try:
            return cls(**data)  # type: ignore[arg-type]
        except TypeError as exc:
            raise ValueError(f"非法 Docker 配置字段：{exc}") from exc


class DockerExecutor:
    """容器执行句柄：每次 run 起一个一次性容器（remove=True，用毕即焚）。"""

    def __init__(self, client: Any, image: str, workdir: str) -> None:
        self._client = client
        self._image = image
        self._workdir = workdir
        self._closed = False

    async def run(self, spec: ExecSpec) -> ExecResult:
        if self._closed:
            raise SandboxError("executor 已关闭，不能复用——重新 acquire 领取")
        try:
            logs = await asyncio.to_thread(
                self._client.containers.run,
                self._image,
                list(spec.command),
                remove=True,
                # 默认断网是硬规则（docs/04 §2）：spec 显式开放才给网络
                network_disabled=not spec.network,
                environment=dict(spec.env) or None,
                working_dir=self._workdir,
                stdout=True,
                stderr=True,
            )
        except Exception as exc:
            exit_code = getattr(exc, "exit_code", None)
            if exit_code is None:
                raise
            return ExecResult(exit_code=exit_code, stderr=str(exc))
        output = logs.decode("utf-8", errors="replace") if isinstance(logs, bytes) else str(logs)
        return ExecResult(exit_code=0, stdout=output)

    async def aclose(self) -> None:
        """归还执行器；容器已 remove，无持久资源。幂等。"""
        self._closed = True


class DockerRuntime(Component):
    """容器沙箱：进程 + 文件系统 + 网络三重隔离。

    docker SDK 惰性导入是架构门禁 4 的硬规则：SDK 未安装或守护进程
    不可用都在 acquire 时报 SandboxUnavailableError，不拖垮安装。
    """

    name = "sandbox-docker"
    provides = (Sandbox,)
    requires = ()
    config_model = DockerConfig

    def __init__(self, config: DockerConfig | None = None) -> None:
        self._config = config if config is not None else DockerConfig()

    def _import_docker(self) -> Any:
        try:
            import docker
        except ImportError as exc:
            raise SandboxUnavailableError("docker SDK 未安装：pip install docker") from exc
        return docker

    async def acquire(self, spec: ExecSpec) -> Executor:
        """连通守护进程并领取执行器；不在这里执行用户代码（docs/04 §2）。"""
        if not spec.command:
            raise SandboxSpecError("ExecSpec.command 不能为空")
        docker = self._import_docker()
        try:
            client = docker.from_env()
            await asyncio.to_thread(client.ping)
        except SandboxUnavailableError:
            raise
        except Exception as exc:
            raise SandboxUnavailableError(f"Docker 守护进程不可用：{exc}") from exc
        return DockerExecutor(client, self._config.image, self._config.workdir)
