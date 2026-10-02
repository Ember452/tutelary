"""门禁 6（docs/05 §4）：examples/only-*.py 全部纳入冒烟——不联网即可跑通。

这是"单点取用"的机器证明：每个组件不经引擎单独可用。示例为空视为
门禁失败（不许存在"还没写示例"的组件）。
"""

import subprocess
import sys

from _walk import EXAMPLES_ROOT, REPO_ROOT


def test_only_examples_smoke():
    examples = sorted(EXAMPLES_ROOT.glob("only-*.py"))
    assert examples, "examples/ 下没有任何 only-* 示例"
    for example in examples:
        result = subprocess.run(
            [sys.executable, str(example)],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=REPO_ROOT,
            check=False,
        )
        assert result.returncode == 0, (
            f"{example.name} 冒烟失败（exit {result.returncode}）\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
