"""发布就绪检查（docs/09 M5）：全量构建 + 门面齐备 + 版本一致。

用法：uv run python scripts/check-release-ready.py
退出码 0 = 就绪；非 0 = 有缺项（逐条列出）。
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

FACADE_FILES = (
    "README.md",
    "LICENSE",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CODE_OF_CONDUCT.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/ISSUE_TEMPLATE/bug_report.md",
    ".github/ISSUE_TEMPLATE/feature_request.md",
    ".github/ISSUE_TEMPLATE/component_proposal.md",
    ".github/workflows/publish.yml",
    ".github/workflows/test.yml",
)

VERSION = "0.1.0"


def main() -> int:
    failures: list[str] = []

    for name in FACADE_FILES:
        if not (REPO_ROOT / name).is_file():
            failures.append(f"缺少门面文件：{name}")

    # 版本 lockstep：九个发行包必须同版本（ADR-0003）
    dist_names: list[str] = []
    for pyproject in sorted((REPO_ROOT / "packages").glob("*/pyproject.toml")):
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        name: str = data["project"]["name"]
        version: str = data["project"]["version"]
        dist_names.append(name)
        if version != VERSION:
            failures.append(f"{name} 版本 {version} != lockstep {VERSION}")
    if len(dist_names) != 9:
        failures.append(f"发行包数量 {len(dist_names)} != 9")

    # 全量构建九个 wheel
    dist_dir = REPO_ROOT / "dist"
    build = subprocess.run(
        ["uv", "build", "--all-packages", "--out-dir", str(dist_dir)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if build.returncode != 0:
        failures.append(f"全量构建失败：\n{build.stderr[-500:]}")
    else:
        for name in dist_names:
            wheel = dist_dir / f"{name.replace('-', '_')}-{VERSION}-py3-none-any.whl"
            if not wheel.is_file():
                failures.append(f"缺少 wheel：{wheel.name}")

    if failures:
        print("发布就绪检查未通过：")
        for failure in failures:
            print(f"  ✗ {failure}")
        return 1
    print(f"发布就绪：{len(dist_names)} 个发行包 v{VERSION}，门面齐备，全量构建成功")
    return 0


if __name__ == "__main__":
    sys.exit(main())
