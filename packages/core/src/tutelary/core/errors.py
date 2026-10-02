"""内核类型化错误。

装配期四错误见 docs/03-kernel.md §6；总线契约错误见 docs/04-contracts.md §3。
捕获方只准捕获这里列出的具体类型——禁止裸 ``except:``（AGENTS §4.5）。
"""


class TutelaryError(Exception):
    """Tutelary 全部类型化错误的基类。"""


class MissingPortError(TutelaryError):
    """装配期：某组件 requires 的端口没有任何提供者。"""


class DuplicatePortError(TutelaryError):
    """装配期：同一端口被多个组件提供。"""


class CircularRequirementError(TutelaryError):
    """装配期：组件间的 requires 图存在环。"""


class ConfigValidationError(TutelaryError):
    """装配期：config 过不了组件的 config_model，或组件声明本身非法。"""


class BusContractError(TutelaryError):
    """总线使用违约：如对流式增量事件注册拦截（docs/04 §3 的硬规则）。"""
