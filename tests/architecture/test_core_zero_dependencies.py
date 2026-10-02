"""门禁 1（docs/05 §4）：core 的 import ⊆ 标准库 ∪ tutelary。

唯一例外：``contract.py`` 是随包发布的 pytest 插件，pytest 属于
``[contract]`` extra 的可选依赖，不进运行时依赖。
"""

import sys

from _walk import import_roots, package_sources


def test_core_zero_dependencies():
    allowed_beyond_stdlib = {"tutelary"}
    violations: list[str] = []
    for source in package_sources("core"):
        is_plugin_module = source.path.name == "contract.py"
        for root in import_roots(source.tree):
            if root in sys.stdlib_module_names:
                continue
            if root in allowed_beyond_stdlib:
                continue
            if root == "pytest" and is_plugin_module:
                continue
            violations.append(f"{source.path}: import {root}")
    assert not violations, "core 出现越界依赖：\n" + "\n".join(violations)
