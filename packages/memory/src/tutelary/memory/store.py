"""Markdown 文件存储：目录布局、frontmatter 编解码与磁盘读写。

布局：``root/<agent>/<session|_global>/<turn_id>.md``。
TurnCommitted 不携带 agent，事件写路径落盘到 ``_shared`` 段——对任意
agent 的召回可见。全部磁盘函数都是阻塞的，调用方必须经
``asyncio.to_thread`` 进入（AGENTS §4.4）；``seed`` 是唯一的同步例外
（测试面，见 docs/04 §4）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from tutelary.core.types import MemoryScope

SHARED_AGENT = "_shared"
"""事件写路径的落盘段：TurnCommitted 不带 agent，对任意 agent 可见。"""

_GLOBAL_SESSION = "_global"
_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]")


@dataclass(frozen=True, slots=True)
class MemoryEntry:
    """一条落盘记忆。"""

    turn_id: str
    agent_id: str
    session_id: str | None
    text: str


def entry_dir(root: Path, agent_id: str, session_id: str | None) -> Path:
    return root / agent_id / (session_id if session_id else _GLOBAL_SESSION)


def safe_stem(turn_id: str) -> str:
    """把 turn_id 规范化成文件名安全片段（危险字符与开头连点一律替换）。"""
    cleaned = _UNSAFE_FILENAME.sub("_", turn_id).lstrip(".")
    return cleaned or "entry"


def entry_path(root: Path, agent_id: str, session_id: str | None, turn_id: str) -> Path:
    return entry_dir(root, agent_id, session_id) / f"{safe_stem(turn_id)}.md"


def serialize(entry: MemoryEntry) -> str:
    session = entry.session_id if entry.session_id is not None else ""
    return (
        "---\n"
        f"turn_id: {entry.turn_id}\n"
        f"agent: {entry.agent_id}\n"
        f"session: {session}\n"
        "---\n"
        f"{entry.text}\n"
    )


def parse(path: Path, agent_dir: str) -> MemoryEntry | None:
    """解析一个 .md 文件；frontmatter 残缺时跳过（返回 None 而不是抛错）。"""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    fields: dict[str, str] = {}
    body = raw
    if raw.startswith("---\n"):
        header, _, rest = raw[4:].partition("\n---\n")
        for line in header.splitlines():
            key, sep, value = line.partition(":")
            if sep:
                fields[key.strip()] = value.strip()
        body = rest
    turn_id = fields.get("turn_id") or path.stem
    session = fields.get("session") or None
    agent = fields.get("agent") or agent_dir
    return MemoryEntry(turn_id=turn_id, agent_id=agent, session_id=session, text=body.strip())


def write_entry(root: Path, entry: MemoryEntry) -> Path:
    """落盘一条记忆（阻塞；经 to_thread 调用）。幂等：目标已存在即跳过。"""
    path = entry_path(root, entry.agent_id, entry.session_id, entry.turn_id)
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize(entry), encoding="utf-8")
    return path


def read_entries(root: Path, scope: MemoryScope) -> list[MemoryEntry]:
    """读取 scope 可见的全部条目（阻塞；经 to_thread 调用）。

    可见性：本 agent 段 + ``_shared`` 段（``_shared`` 只解除 agent 隔离，
    会话过滤照常生效）；agent 级查询（session=None）看到该 agent 全部
    会话与全局条目。顺序 = 文件名字典序——引擎用单调 turn_id 时即时间序。
    """
    agent_dirs = [root / scope.agent_id, root / SHARED_AGENT]
    entries: list[MemoryEntry] = []
    for agent_dir in agent_dirs:
        if not agent_dir.is_dir():
            continue
        for path in sorted(agent_dir.rglob("*.md")):
            entry = parse(path, agent_dir.name)
            if entry is None:
                continue
            if _visible(entry, scope):
                entries.append(entry)
    return entries


def _visible(entry: MemoryEntry, scope: MemoryScope) -> bool:
    if entry.agent_id not in (scope.agent_id, SHARED_AGENT):
        return False
    if entry.session_id is None or scope.session_id is None:
        return True
    return entry.session_id == scope.session_id
