"""ports.py：端口协议与 fakes 的结构对应（方法层冒烟）。"""

from tutelary.core.events import Bus
from tutelary.core.fakes import FakeBus, FakeMemory, FakeProvider, FakeSandbox
from tutelary.core.ports import Memory, Provider, Sandbox


def test_fakes_satisfy_their_port_surface():
    # runtime_checkable 协议只查方法存在性；深度行为由各自的测试保证
    assert isinstance(FakeProvider(), Provider)
    assert isinstance(FakeMemory(), Memory)
    assert isinstance(FakeSandbox(), Sandbox)
    assert isinstance(FakeBus(), Bus)
