"""随契约发布的零依赖假实现（docs/08 §2）。

三个作用：组件包与下游用户的测试不依赖真实 LLM / Docker；only-* 示例的
"不联网"由这里供给；第三方实现有行为基线可对照。内置实现与第三方实现
无特权——它们也要另写实现并通过契约套件。
"""

from tutelary.core.fakes._bus import FakeBus
from tutelary.core.fakes._memory import FakeMemory
from tutelary.core.fakes._provider import FakeProvider
from tutelary.core.fakes._sandbox import FakeExecutor, FakeSandbox

__all__ = ["FakeBus", "FakeExecutor", "FakeMemory", "FakeProvider", "FakeSandbox"]
