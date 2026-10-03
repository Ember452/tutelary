"""mem0 adapter 的类型化错误。"""

from tutelary.core.errors import TutelaryError


class Mem0AdapterError(TutelaryError):
    """Mem0 adapter 错误的基类。"""


class Mem0UnavailableError(Mem0AdapterError):
    """mem0ai 未安装（惰性导入失败）——安装 extra：pip install 'tutelary-mem0-adapter[mem0]'。"""
