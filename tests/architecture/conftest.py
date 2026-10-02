"""架构门禁的取材层：解析 packages/ 下的源码为 AST。

sys.path 引导让测试文件可以 ``import _walk``——与 pytest 的
--import-mode=importlib 共存的最稳办法。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
