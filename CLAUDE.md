# CLAUDE.md

All behavioral guidelines and project rules live in **[AGENTS.md](AGENTS.md)** —
read it before writing any code. This file is a pointer, not a copy; do not
fork rules into here.

Quick reminders (full details in AGENTS.md):

- Python 3.13 + uv workspace + ruff + pytest; one wheel per `packages/*`
  directory (`tutelary-<sub>` ↔ `tutelary.<sub>`).
- **Never `git commit` or `git push`** — the user runs those. Report changes
  and let the user decide.
- Contracts in `docs/03` / `docs/04` are working drafts until first release
  (M5): code decides, docs follow — update them in the same task.
- If an architecture test, contract suite, or `only-*` example blocks you,
  stop and surface it. Never disable the judges.
- Quality constraints bound how code is written, never what gets built.
