"""隔离安装测试的共享装置（docs/05 §5）：构建全部发行 wheel，一次。"""

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DIST_NAMES = ("tutelary-core", "tutelary-context", "tutelary-memory")


@pytest.fixture(scope="session")
def built_wheels(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("wheels")
    for dist_name in DIST_NAMES:
        subprocess.run(
            ["uv", "build", "--package", dist_name, "--out-dir", str(out)],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
        )
    return out
