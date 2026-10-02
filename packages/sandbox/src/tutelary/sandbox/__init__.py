"""Tutelary 执行隔离：Subprocess 与 Docker 两个运行时，同一 Sandbox 端口。

只依赖 core；docker SDK 是惰性导入的可选依赖（架构门禁 4 强制），
未安装时 DockerRuntime 报类型化错误而不是拖垮安装。
"""

from tutelary.sandbox.errors import SandboxError, SandboxSpecError, SandboxUnavailableError

__all__ = ["SandboxError", "SandboxSpecError", "SandboxUnavailableError"]
