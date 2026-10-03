"""门禁 2（docs/05 §4）：组件包只准 import core 与自身子模块——零横向依赖。

豁免：伞包 runtime 是组装者（docs/05 §3），准许依赖全部组件；伞包
只进不出由门禁 3 看守。
"""

from _walk import absolute_imports, component_names, package_sources


def test_no_horizontal_imports():
    all_names = component_names()
    violations: list[str] = []
    for name in all_names:
        allowed_subpackages = {"core", *all_names} if name == "runtime" else {"core", name}
        for source in package_sources(name):
            for module in absolute_imports(source.tree):
                # 只看 tutelary 命名空间：第三方形态的顶层名（如
                # tutelary_mem0_adapter.*）是包自己的子模块，不受此门禁管
                if module != "tutelary" and not module.startswith("tutelary."):
                    continue
                parts = module.split(".")
                sub = parts[1] if len(parts) > 1 else ""
                if sub not in allowed_subpackages:
                    violations.append(f"{source.path}: import {module}")
    assert not violations, "组件出现横向依赖：\n" + "\n".join(violations)
