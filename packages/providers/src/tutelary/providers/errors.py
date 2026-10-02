"""providers 的类型化错误（挂在 core 的 TutelaryError 体系之下，AGENTS §4.5）。"""

from tutelary.core.errors import TutelaryError


class ProviderError(TutelaryError):
    """provider 请求失败：重试耗尽、故障转移穷尽或流中途失败。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
