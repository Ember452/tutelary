"""offload.py：寄存/取回往返与未命中错误。"""

import pytest

from tutelary.context.errors import OffloadMissError
from tutelary.context.offload import OffloadStore


def test_put_then_get_roundtrips():
    store = OffloadStore()
    store.put("call-1", "原始输出")
    assert store.get("call-1") == "原始输出"


def test_same_ref_overwrites():
    store = OffloadStore()
    store.put("call-1", "旧")
    store.put("call-1", "新")
    assert store.get("call-1") == "新"
    assert len(store) == 1


def test_missing_ref_raises_typed_error():
    store = OffloadStore()
    with pytest.raises(OffloadMissError, match="call-x"):
        store.get("call-x")
