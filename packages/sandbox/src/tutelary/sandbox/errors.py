"""sandbox 的类型化错误（挂在 core 的 TutelaryError 体系之下，AGENTS §4.5）。"""

from tutelary.core.errors import TutelaryError


class SandboxError(TutelaryError):
    """sandbox 组件错误的基类。"""


class SandboxUnavailableError(SandboxError):
    """运行时不可用：docker SDK 未安装，或容器守护进程无法访问。"""


class SandboxSpecError(SandboxError):
    """ExecSpec 非法：如命令为空。"""
