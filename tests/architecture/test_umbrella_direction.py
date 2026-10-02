"""门禁 3（docs/05 §4）：伞包只进不出——任何子包禁止 import tutelary.runtime。"""

from _walk import absolute_imports, component_names, package_sources


def test_umbrella_direction():
    violations: list[str] = []
    for name in ("core", *component_names()):
        for source in package_sources(name):
            for module in absolute_imports(source.tree):
                if module.startswith("tutelary.runtime"):
                    violations.append(f"{source.path}: import {module}")
    assert not violations, "出现对伞包的逆向依赖：\n" + "\n".join(violations)
