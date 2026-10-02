"""契约测试套件的 pytest 插件骨架（docs/04 §4）。

随 tutelary-core 发布：``pip install "tutelary-core[contract]"`` 后，
``pytest --tutelary-contract=<port> --tutelary-factory=<dotted.path>``
对任意实现跑同一套契约检查——内置实现与第三方实现无特权。

M0 只交付选项解析与占位：请求尚未就绪的端口会得到明确的 UsageError
而不是静默跳过。memory 套件随 M2 落地，其余端口随组件阶段补齐。
"""

from __future__ import annotations

import pytest

# port 名 → 套件入口；M2 起填充（memory 是第一个）
_SUITES: dict[str, str] = {}


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("tutelary")
    group.addoption(
        "--tutelary-contract",
        action="store",
        default=None,
        metavar="PORT",
        help="运行指定端口的契约测试套件（如 memory）。",
    )
    group.addoption(
        "--tutelary-factory",
        action="store",
        default=None,
        metavar="DOTTED.PATH",
        help="被测实现的工厂函数（点分路径），返回端口实例。",
    )


def pytest_configure(config: pytest.Config) -> None:
    port = config.getoption("--tutelary-contract")
    if port is None:
        return
    if port not in _SUITES:
        raise pytest.UsageError(
            f"tutelary 契约套件 '{port}' 尚未就绪：M0 只交付插件骨架，"
            f"memory 套件随 M2 落地。可用套件：{sorted(_SUITES) or '（暂无）'}"
        )
