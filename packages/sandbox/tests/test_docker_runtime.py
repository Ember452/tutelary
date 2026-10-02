"""DockerRuntime：SDK 缺失路径、配置校验、spec 校验（全部离线可测）。"""

import pytest

from tutelary.core.types import ExecSpec
from tutelary.sandbox.docker_runtime import DockerConfig, DockerRuntime
from tutelary.sandbox.errors import SandboxSpecError, SandboxUnavailableError


async def test_missing_docker_sdk_raises_unavailable(monkeypatch: pytest.MonkeyPatch):
    # 强制"SDK 未安装"路径，宿主机装没装 docker 都能测
    monkeypatch.setitem(__import__("sys").modules, "docker", None)
    runtime = DockerRuntime()
    with pytest.raises(SandboxUnavailableError, match="SDK 未安装"):
        await runtime.acquire(ExecSpec(command=("echo", "hi")))


def test_config_rejects_unknown_fields():
    with pytest.raises(ValueError, match="非法 Docker 配置"):
        DockerConfig.model_validate({"image": "x", "nope": 1})


async def test_empty_command_raises_spec_error():
    runtime = DockerRuntime()
    with pytest.raises(SandboxSpecError, match="不能为空"):
        await runtime.acquire(ExecSpec(command=()))
