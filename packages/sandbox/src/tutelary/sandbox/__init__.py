"""Tutelary 执行隔离：Subprocess 与 Docker 两个运行时，同一 Sandbox 端口。

只依赖 core；docker SDK 是惰性导入的可选依赖（架构门禁 4 强制），
未安装时 DockerRuntime 报类型化错误而不是拖垮安装。Subprocess 无
网络隔离（诚实声明见 subprocess_runtime 模块）；真断网用 Docker。
"""

from tutelary.sandbox._subprocess import DEFAULT_TIMEOUT_SECONDS, SubprocessExecutor
from tutelary.sandbox.docker_runtime import DockerConfig, DockerExecutor, DockerRuntime
from tutelary.sandbox.errors import SandboxError, SandboxSpecError, SandboxUnavailableError
from tutelary.sandbox.subprocess_runtime import SubprocessRuntime

__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "DockerConfig",
    "DockerExecutor",
    "DockerRuntime",
    "SandboxError",
    "SandboxSpecError",
    "SandboxUnavailableError",
    "SubprocessExecutor",
    "SubprocessRuntime",
]
