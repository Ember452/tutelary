"""门禁 2（docs/05 §4）：组件包只准 import core 与自身子模块——零横向依赖。"""

from _walk import absolute_imports, component_names, package_sources


def test_no_horizontal_imports():
    violations: list[str] = []
    for name in component_names():
        allowed_subpackages = {"core", name}
        for source in package_sources(name):
            for module in absolute_imports(source.tree):
                if not module.startswith("tutelary"):
                    continue
                parts = module.split(".")
                sub = parts[1] if len(parts) > 1 else ""
                if sub not in allowed_subpackages:
                    violations.append(f"{source.path}: import {module}")
    assert not violations, "组件出现横向依赖：\n" + "\n".join(violations)
