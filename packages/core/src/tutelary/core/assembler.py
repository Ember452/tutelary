"""装配器：声明式依赖的 fail-fast 解析（docs/03 §6）。

顺序固定：建端口供需图 → 校验（缺端口 / 重复提供 / 环 / 配置 / 组件名）
→ 拓扑序实例化构造注入 → 依序 setup 入 effect 栈，任一步失败回滚已
setup 的组件后再抛错。``Tutelary`` 句柄仅限组合根与测试使用（ADR-0001）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, TypeVar

from tutelary.core.errors import (
    CircularRequirementError,
    ConfigValidationError,
    DuplicatePortError,
    MissingPortError,
)
from tutelary.core.lifecycle import EffectStack

T = TypeVar("T")


@dataclass(slots=True)
class _Registration:
    component: type[Any]
    config: Mapping[str, Any] | None


def _provides(component: type[Any]) -> tuple[type, ...]:
    # 鸭子读取：组件不强制继承 Component（config_model 同规），声明即参与装配
    return getattr(component, "provides", ())


def _requires(component: type[Any]) -> tuple[type, ...]:
    return getattr(component, "requires", ())


def _config_model(component: type[Any]) -> type | None:
    return getattr(component, "config_model", None)


class Assembler:
    """组合根的装配入口：``use()`` 声明组件，``assemble()`` 一次性解析。

    同一个 Assembler 可重复 ``assemble()``，每次产出独立的 ``Tutelary``。
    """

    def __init__(self) -> None:
        self._registrations: list[_Registration] = []

    def use(self, component: type[Any], config: Mapping[str, Any] | None = None) -> Assembler:
        """登记一个组件及其可选配置映射；返回自身以支持链式调用。"""
        self._registrations.append(_Registration(component=component, config=config))
        return self

    async def assemble(self) -> Tutelary:
        """按 docs/03 §6 的固定顺序装配；任何校验失败立即抛类型化错误。"""
        regs = list(self._registrations)
        provider_of = _index_providers(regs)
        _check_unique_names(regs)
        _check_required_ports(regs, provider_of)
        order = _topological_order(regs, provider_of)

        instances: dict[str, Any] = {}
        by_port: dict[type, Any] = {}
        stack = EffectStack()
        try:
            for reg in order:
                deps = tuple(
                    instances[provider_of[port].component.name] for port in _requires(reg.component)
                )
                instance = (
                    reg.component(*deps, config=_validated_config(reg))
                    if reg.config is not None or _config_model(reg.component) is not None
                    else reg.component(*deps)
                )
                instances[reg.component.name] = instance
                for port in _provides(reg.component):
                    by_port[port] = instance
            for reg in order:
                instance = instances[reg.component.name]
                setup = getattr(instance, "setup", None)
                # 鸭子组件可以没有 setup——没声明即视为无副作用
                stack.push(setup() if setup is not None else None)
        except BaseException:
            # 装配中途失败不留半拉子状态：BaseException（含 CancelledError）
            # 也先回滚再上抛（AGENTS §4.4 不吞取消）。
            await stack.unwind()
            raise

        return Tutelary(instances=by_port, stack=stack)


class Tutelary:
    """装配结果句柄：类型化端口访问 + 整船 shutdown。

    仅限组合根与测试持有；组件内部禁止持有整船句柄（ADR-0001）。
    """

    def __init__(self, instances: Mapping[type, Any], stack: EffectStack) -> None:
        self._instances = dict(instances)
        self._stack = stack

    def get(self, port: type[T]) -> T:
        """按端口类型取实例；端口未被任何组件提供时抛 MissingPortError。"""
        try:
            return self._instances[port]  # type: ignore[return-value]
        except KeyError:
            raise MissingPortError(f"端口 {port.__name__} 未被任何组件提供") from None

    async def shutdown(self) -> None:
        """整船下线：effect 栈 LIFO 逆序回滚全部已登记副作用。"""
        await self._stack.unwind()


def _index_providers(regs: list[_Registration]) -> dict[type, _Registration]:
    provider_of: dict[type, _Registration] = {}
    for reg in regs:
        for port in _provides(reg.component):
            if port in provider_of:
                raise DuplicatePortError(
                    f"端口 {port.__name__} 被多次提供："
                    f"{provider_of[port].component.name} 与 {reg.component.name}"
                )
            provider_of[port] = reg
    return provider_of


def _check_unique_names(regs: list[_Registration]) -> None:
    seen: set[str] = set()
    for reg in regs:
        if not getattr(reg.component, "name", None):
            raise ConfigValidationError(
                f"组件 {reg.component.__name__} 缺少 name（装配日志与错误定位需要）"
            )
        if reg.component.name in seen:
            raise ConfigValidationError(f"组件名重复：{reg.component.name}")
        seen.add(reg.component.name)


def _check_required_ports(
    regs: list[_Registration], provider_of: Mapping[type, _Registration]
) -> None:
    for reg in regs:
        for port in _requires(reg.component):
            if port not in provider_of:
                raise MissingPortError(
                    f"组件 {reg.component.name} requires 端口 {port.__name__}，无提供者"
                )


def _topological_order(
    regs: list[_Registration], provider_of: Mapping[type, _Registration]
) -> list[_Registration]:
    by_name = {reg.component.name: reg for reg in regs}
    state: dict[str, int] = {name: 0 for name in by_name}  # 0 未访 / 1 在栈 / 2 完成
    order: list[_Registration] = []

    def visit(name: str, path: list[str]) -> None:
        if state[name] == 1:
            cycle = [*path[path.index(name) :], name]
            raise CircularRequirementError("requires 环：" + " -> ".join(cycle))
        if state[name] == 2:
            return
        state[name] = 1
        path.append(name)
        for port in _requires(by_name[name].component):
            visit(provider_of[port].component.name, path)
        path.pop()
        state[name] = 2
        order.append(by_name[name])

    for name in by_name:
        if state[name] == 0:
            visit(name, [])
    return order


def _validated_config(reg: _Registration) -> Any:
    model = _config_model(reg.component)
    if model is None:
        return reg.config
    validate = getattr(model, "model_validate", None)
    if validate is None:
        raise ConfigValidationError(
            f"组件 {reg.component.name} 的 config_model 缺少 model_validate(dict)"
        )
    try:
        return validate(dict(reg.config) if reg.config is not None else {})
    except Exception as exc:
        raise ConfigValidationError(f"组件 {reg.component.name} 配置校验失败：{exc}") from exc
