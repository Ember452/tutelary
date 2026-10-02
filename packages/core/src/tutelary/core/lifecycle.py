"""生命周期原语：Component、Disposable 与 effect 栈（docs/03 §5）。

时间可组合性的落点：组件 setup() 的返回值、事件订阅的返回值全部登记在
effect 栈上；组件卸载、装配中途失败、整船 shutdown 都走同一条 LIFO 回滚路径。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, ClassVar, Protocol, runtime_checkable


@runtime_checkable
class SupportsAclose(Protocol):
    """实现 ``aclose()`` 的可清理对象（异步生成器、连接句柄等）。"""

    def aclose(self) -> Awaitable[None]: ...


type Cleanup = Callable[[], Awaitable[None] | None]
"""同步或异步的零参清理函数。返回 awaitable 则被等待，返回 None 则视为完成。"""

type Disposable = Cleanup | SupportsAclose
"""一份可登记进 effect 栈的清理承诺：清理函数，或带 ``aclose()`` 的对象。"""

type PortSpec = tuple[type, ...]
"""组件 provides/requires 声明的端口类型序列。"""


async def run_disposable(item: Disposable) -> None:
    """执行一份清理承诺；带 ``aclose()`` 的对象优先走 ``aclose()``。"""
    result = item.aclose() if isinstance(item, SupportsAclose) else item()
    if result is not None:
        await result


@dataclass(slots=True)
class EffectStack:
    """LIFO 清理栈。

    契约：``unwind`` 按登记的逆序执行；单条清理失败不阻断其余，全部跑完后
    以 ``ExceptionGroup`` 聚合上抛。``BaseException``（含 ``CancelledError``）
    不聚合、立即上抛——剩余清理项保留在栈上，允许再次 ``unwind`` 续跑。
    """

    items: list[Disposable] = field(default_factory=list)

    def push(self, item: Disposable | None) -> None:
        """登记一份清理承诺；None 合法（setup 返回 None 表示无副作用）。"""
        if item is not None:
            self.items.append(item)

    async def unwind(self) -> None:
        """LIFO 逆序执行全部清理项；语义见类 docstring。"""
        errors: list[Exception] = []
        while self.items:
            item = self.items.pop()
            try:
                await run_disposable(item)
            except Exception as exc:
                errors.append(exc)
        if errors:
            raise ExceptionGroup("effect 栈回滚时有清理项失败", errors)


class Component:
    """组件基类：provides/requires 声明端口供需，setup() 登记副作用。

    装配器按 ``requires`` 声明顺序位置注入端口实例，``config`` 以关键字
    注入。``config_model`` 是鸭子类型协议——有 ``model_validate(dict)``
    即可，兼容 pydantic 但不依赖它（docs/03 §5）。子类通常覆写
    ``__init__`` 收窄依赖签名；基类的实现只做原样保存。
    """

    name: ClassVar[str]
    provides: ClassVar[PortSpec] = ()
    requires: ClassVar[PortSpec] = ()
    config_model: ClassVar[type | None] = None

    def __init__(self, *deps: Any, config: Any = None) -> None:
        self._deps = deps
        self._config = config

    def setup(self) -> Disposable | None:
        """登记副作用（订阅、连接、启动后台任务），返回清理承诺或 None。"""
        return None
