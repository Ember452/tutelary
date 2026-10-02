"""store.py：目录布局、frontmatter 编解码、可见性与幂等落盘。"""

from pathlib import Path

from tutelary.core.types import MemoryScope
from tutelary.memory.store import (
    MemoryEntry,
    entry_path,
    parse,
    read_entries,
    safe_stem,
    write_entry,
)


def _entry(
    turn_id: str = "t1", agent: str = "a1", session: str | None = "s1", text: str = "正文"
) -> MemoryEntry:
    return MemoryEntry(turn_id=turn_id, agent_id=agent, session_id=session, text=text)


def test_serialize_roundtrip_via_disk(tmp_path: Path):
    entry = _entry()
    path = write_entry(tmp_path, entry)
    assert parse(path, "a1") == entry


def test_write_is_idempotent_per_turn_id(tmp_path: Path):
    write_entry(tmp_path, _entry())
    path_again = write_entry(tmp_path, _entry(text="改写的内容"))
    parsed = parse(path_again, "a1")
    assert parsed is not None
    assert parsed.text == "正文"


def test_unsafe_turn_id_stays_inside_scope_dir(tmp_path: Path):
    path = write_entry(tmp_path, _entry(turn_id="../evil"))
    assert path.parent == tmp_path / "a1" / "s1"
    assert ".." not in path.name


def test_global_session_lands_in_global_dir(tmp_path: Path):
    path = write_entry(tmp_path, _entry(session=None))
    assert path.parent == tmp_path / "a1" / "_global"


def test_visibility_agent_and_session(tmp_path: Path):
    write_entry(tmp_path, _entry(turn_id="own"))
    write_entry(tmp_path, _entry(turn_id="shared", agent="_shared", session="s2"))
    write_entry(tmp_path, _entry(turn_id="shared-global", agent="_shared", session=None))
    write_entry(tmp_path, _entry(turn_id="other-agent", agent="a2"))
    write_entry(tmp_path, _entry(turn_id="other-session", session="s9"))

    # _shared 只解除 agent 隔离，会话过滤照常生效
    seen = {e.turn_id for e in read_entries(tmp_path, MemoryScope(agent_id="a1", session_id="s1"))}
    assert seen == {"own", "shared-global"}

    seen_agent_wide = {e.turn_id for e in read_entries(tmp_path, MemoryScope(agent_id="a1"))}
    assert seen_agent_wide == {"own", "other-session", "shared", "shared-global"}


def test_read_entries_on_missing_root_is_empty(tmp_path: Path):
    assert read_entries(tmp_path / "nope", MemoryScope(agent_id="a1")) == []


def test_parse_tolerates_broken_frontmatter(tmp_path: Path):
    scope_dir = tmp_path / "a1" / "s1"
    scope_dir.mkdir(parents=True)
    file = scope_dir / "weird.md"
    file.write_text("不是 frontmatter 的正文", encoding="utf-8")
    entry = parse(file, "a1")
    assert entry is not None
    assert entry.turn_id == "weird"
    assert entry.agent_id == "a1"
    assert entry.text == "不是 frontmatter 的正文"


def test_expected_layout_matches_entry_path(tmp_path: Path):
    assert entry_path(tmp_path, "a1", "s1", "t1") == tmp_path / "a1" / "s1" / "t1.md"


def test_safe_stem_replaces_unsafe_characters():
    assert safe_stem("t/1:x") == "t_1_x"
    assert safe_stem("") == "entry"
