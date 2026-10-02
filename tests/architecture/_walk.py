"""AST import 图的最小工具集：供六条架构门禁共用。"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES_ROOT = REPO_ROOT / "packages"
EXAMPLES_ROOT = REPO_ROOT / "examples"


@dataclass(frozen=True, slots=True)
class SourceFile:
    """一个被门禁扫描的源文件与其 AST。"""

    path: Path
    tree: ast.Module


def parse_sources(root: Path) -> list[SourceFile]:
    """解析 root 下全部 .py 文件；路径排序保证断言消息稳定。"""
    return sorted(
        (
            SourceFile(path=p, tree=ast.parse(p.read_text(encoding="utf-8")))
            for p in root.rglob("*.py")
        ),
        key=lambda source: source.path,
    )


def package_sources(name: str) -> list[SourceFile]:
    return parse_sources(PACKAGES_ROOT / name / "src")


def component_names() -> list[str]:
    """packages/ 下除 core 外的组件目录名（无 src 的目录视为未开工）。"""
    return sorted(
        entry.name
        for entry in PACKAGES_ROOT.iterdir()
        if entry.is_dir() and entry.name != "core" and (entry / "src").is_dir()
    )


def absolute_imports(tree: ast.Module) -> set[str]:
    """全部绝对 import 的完整模块名。"""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module)
    return names


def import_roots(tree: ast.Module) -> set[str]:
    """全部绝对 import 的顶层模块名（相对 import 是包内事务，不参与）。"""
    return {name.split(".")[0] for name in absolute_imports(tree)}


def module_level_imports(tree: ast.Module) -> list[str]:
    """模块作用域的 import 完整名——不进入函数/类体（惰性导入的合法位置）。"""

    def scan(body: list[ast.stmt]) -> list[str]:
        found: list[str] = []
        for node in body:
            match node:
                case ast.Import():
                    found.extend(alias.name for alias in node.names)
                case ast.ImportFrom():
                    found.append(node.module or "")
                case ast.If():
                    found.extend(scan(node.body))
                    found.extend(scan(node.orelse))
                case ast.Try() | ast.TryStar():
                    for handler in node.handlers:
                        found.extend(scan(handler.body))
                    found.extend(scan(node.body))
                    found.extend(scan(node.orelse))
                    found.extend(scan(node.finalbody))
                case ast.With():
                    found.extend(scan(node.body))
        return found

    return [name for name in scan(tree.body) if name]
