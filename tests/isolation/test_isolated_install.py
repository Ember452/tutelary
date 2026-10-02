"""隔离安装（docs/05 §5）：每包一个干净 venv，只装该包 + core + 测试依赖跑包内测试。

这是"每个组件独立可装"的机器证明——任何"顺手 import 兄弟包"或
"顶层拖进重依赖"都会在这里爆红。矩阵随 packages/ 增长。
"""

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DIST_NAMES = {
    "core": "tutelary-core",
    "context": "tutelary-context",
    "memory": "tutelary-memory",
    "policy": "tutelary-policy",
}


def _wheel_for(built_wheels: Path, dist_name: str) -> Path:
    # wheel 文件名把发行名的连字符规范化成下划线
    matches = sorted(built_wheels.glob(f"{dist_name.replace('-', '_')}-*.whl"))
    assert matches, f"缺少 {dist_name} 的 wheel"
    return matches[0]


@pytest.mark.parametrize("package", sorted(DIST_NAMES))
def test_isolated_install(package: str, built_wheels: Path, tmp_path: Path):
    venv = tmp_path / "venv"
    subprocess.run(
        ["uv", "venv", "-q", "--python", "3.13", str(venv)], check=True, capture_output=True
    )
    python = venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    wanted = [
        _wheel_for(built_wheels, "tutelary-core"),
        _wheel_for(built_wheels, DIST_NAMES[package]),
    ]
    # 包内测试需要 pytest + pytest-asyncio（asyncio_mode=auto 来自根配置）
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "-q",
            "--python",
            str(python),
            *wanted,
            "pytest",
            "pytest-asyncio",
        ],
        check=True,
        capture_output=True,
    )
    package_tests = REPO_ROOT / "packages" / package / "tests"
    result = subprocess.run(
        [
            str(python),
            "-m",
            "pytest",
            str(package_tests),
            "-q",
            "--import-mode=importlib",
            "-p",
            "no:cacheprovider",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert result.returncode == 0, f"{package} 隔离安装测试失败：\n{result.stdout}\n{result.stderr}"
