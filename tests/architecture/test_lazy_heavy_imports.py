"""门禁 4（docs/05 §4）：docker/grpc/torch 等重依赖禁止出现在模块顶层（函数体内合法）。"""

from _walk import component_names, module_level_imports, package_sources

HEAVY_MODULES = frozenset({"docker", "grpc", "torch"})


def test_lazy_heavy_imports():
    violations: list[str] = []
    for name in ("core", *component_names()):
        for source in package_sources(name):
            for module in module_level_imports(source.tree):
                if module.split(".")[0] in HEAVY_MODULES:
                    violations.append(f"{source.path}: 顶层 import {module}")
    assert not violations, "重依赖必须惰性导入：\n" + "\n".join(violations)
