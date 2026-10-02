"""契约测试套件的 pytest 插件（docs/04 §4）。

随 tutelary-core 发布：``pip install "tutelary-core[contract]"`` 后，
``pytest --tutelary-contract=<port> --tutelary-factory=<dotted.path>``
对任意实现跑同一套契约检查——内置实现与第三方实现无特权。

套件发现：各实现包经入口点组 ``tutelary.contract_suites`` 注册
（port 名 → 套件模块），core 只做发现与执行——内核保持零依赖、零反向
import。工厂契约：``--tutelary-factory`` 直接指向被测**组件类**；
套件用 core 装配器与 core fakes 把它装配起来驱动——契约检查的不只是
行为，还有"能作为组件被装配"本身。
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from importlib.metadata import entry_points
from typing import Any

import pytest

_SUITES_GROUP = "tutelary.contract_suites"


@dataclass(frozen=True, slots=True)
class _ContractPlan:
    """一次契约运行的全部材料：端口名、套件模块、被测组件类。"""

    port: str
    suite: Any
    component_class: type[Any]


_ContractKey = pytest.StashKey[_ContractPlan]()


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("tutelary")
    group.addoption(
        "--tutelary-contract",
        action="store",
        default=None,
        metavar="PORT",
        help="运行指定端口的契约测试套件（如 context / memory）。",
    )
    group.addoption(
        "--tutelary-factory",
        action="store",
        default=None,
        metavar="DOTTED.PATH",
        help="被测组件类的点分路径（'模块:属性'）。",
    )


def pytest_configure(config: pytest.Config) -> None:
    port = config.getoption("--tutelary-contract")
    if port is None:
        return
    suites = {ep.name: ep for ep in entry_points(group=_SUITES_GROUP)}
    if port not in suites:
        raise pytest.UsageError(
            f"tutelary 契约套件 '{port}' 未注册。可用套件：{sorted(suites) or '（暂无）'}"
            f"——各实现包经入口点组 {_SUITES_GROUP} 注册。"
        )
    factory_path = config.getoption("--tutelary-factory")
    if not factory_path:
        raise pytest.UsageError(
            "--tutelary-contract 需要配套 --tutelary-factory=<dotted.path>（指向被测组件类）"
        )
    config.stash[_ContractKey] = _ContractPlan(
        port=port, suite=suites[port].load(), component_class=_load_component_class(factory_path)
    )


def pytest_collection_modifyitems(
    session: pytest.Session, config: pytest.Config, items: list[pytest.Item]
) -> None:
    plan = config.stash.get(_ContractKey, None)
    if plan is None:
        return
    items.append(
        ContractItem.from_parent(session, name=f"tutelary-contract::{plan.port}", plan=plan)
    )


class ContractCheckFailed(Exception):
    """契约检查未全部通过（逐项列在消息里）。"""


class ContractItem(pytest.Item):
    """单条契约检查项：装配工厂给出的组件类，执行套件的 run_checks。"""

    def __init__(self, *, plan: _ContractPlan, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._plan = plan

    def runtest(self) -> None:
        results = self._plan.suite.run_checks(self._plan.component_class)
        failures = [f"  ✗ {name}: {detail}" for name, ok, detail in results if not ok]
        if failures:
            raise ContractCheckFailed(
                f"契约套件 '{self._plan.port}' 有 {len(failures)} 项未过：\n" + "\n".join(failures)
            )

    def repr_failure(self, excinfo: pytest.ExceptionInfo[BaseException]) -> object:
        # 基类可返回 TerminalRepr（pytest 未公开其类型），故放宽为 object
        if isinstance(excinfo.value, ContractCheckFailed):
            return str(excinfo.value)
        return super().repr_failure(excinfo)

    def reportinfo(self) -> tuple[str, int, str]:
        return f"tutelary-contract::{self._plan.port}", 0, f"tutelary 契约套件 {self._plan.port}"


def _load_component_class(dotted: str) -> type[Any]:
    module_path, _, attr = dotted.partition(":")
    if not module_path or not attr:
        raise pytest.UsageError(f"--tutelary-factory 需要 '模块:属性' 形式，得到 {dotted!r}")
    obj: Any = import_module(module_path)
    for part in attr.split("."):
        obj = getattr(obj, part)
    if not isinstance(obj, type):
        raise pytest.UsageError(f"--tutelary-factory 必须指向组件类，得到 {obj!r}")
    return obj
