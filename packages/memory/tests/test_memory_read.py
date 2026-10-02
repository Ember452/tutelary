"""MarkdownProvider 读路径：种子召回、无命中不抛错、配置校验。"""

from pathlib import Path

import pytest

from tutelary.core.fakes import FakeBus
from tutelary.core.types import MemoryScope
from tutelary.memory.errors import MarkdownMemoryError
from tutelary.memory.provider import DEFAULT_ROOT, MarkdownMemoryConfig, MarkdownProvider

_SCOPE = MemoryScope(agent_id="a1", session_id="s1")


def _provider(tmp_path: Path) -> MarkdownProvider:
    return MarkdownProvider(FakeBus(), config=MarkdownMemoryConfig(root=tmp_path))


def test_config_defaults_to_cwd_store():
    config = MarkdownMemoryConfig.model_validate({})
    assert config.root == DEFAULT_ROOT


def test_config_rejects_file_as_root(tmp_path: Path):
    file = tmp_path / "not-a-dir"
    file.write_text("x", encoding="utf-8")
    with pytest.raises(MarkdownMemoryError, match="不是目录"):
        MarkdownMemoryConfig.model_validate({"root": str(file)})


async def test_seed_then_recall_hits_same_scope(tmp_path: Path):
    provider = _provider(tmp_path)
    provider.seed(_SCOPE, "回滚预案在周五窗口执行")
    hits = await provider.recall("周五", _SCOPE)
    assert [hit.text for hit in hits] == ["回滚预案在周五窗口执行"]


async def test_recall_other_scope_returns_empty_without_error(tmp_path: Path):
    provider = _provider(tmp_path)
    provider.seed(_SCOPE, "秘密")
    assert await provider.recall("秘密", MemoryScope(agent_id="a2", session_id="s1")) == []


async def test_recall_on_empty_root_returns_empty_without_error(tmp_path: Path):
    provider = _provider(tmp_path)
    assert await provider.recall("任何", _SCOPE) == []


async def test_empty_query_recalls_everything_in_scope(tmp_path: Path):
    provider = _provider(tmp_path)
    provider.seed(_SCOPE, "第一条")
    provider.seed(_SCOPE, "第二条")
    assert len(await provider.recall("", _SCOPE)) == 2


async def test_load_context_contains_seed_text(tmp_path: Path):
    provider = _provider(tmp_path)
    provider.seed(_SCOPE, "预算 100k")
    context = await provider.load_context("预算", _SCOPE)
    assert "预算 100k" in context


def test_seed_ids_are_unique_per_scope(tmp_path: Path):
    provider = _provider(tmp_path)
    first = provider.seed(_SCOPE, "一")
    second = provider.seed(_SCOPE, "二")
    assert first != second
