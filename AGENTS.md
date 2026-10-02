# AGENTS.md — Tutelary Development Guidelines

Behavioral guidelines and project rules for AI-assisted development on Tutelary.
Merge with task-specific instructions as needed.

**Tradeoff:** these guidelines bias toward caution over speed. For trivial
tasks, use judgment; when unsure, follow them.

## 0. What This Project Is

Tutelary is a governance-first, component-based agent infrastructure: each
capability (context governance, memory, sandbox, policy, LLM providers, agent
loop) is an independently installable package, stitched together by a thin,
zero-dependency kernel. Nothing here is a monolithic framework — if you find
yourself coupling components together, you are working against the design.

Read before touching code:

- `docs/README.md` — documentation map
- `docs/02-philosophy.md` / `docs/03-kernel.md` — the kernel's shape
- `docs/04-contracts.md` — ports, events, component obligations
- `docs/08-structure.md` — repository layout (authoritative)
- `docs/09-development-plan.md` — current phase and status

Signatures in `docs/03` / `docs/04` are **working drafts**: before the first
public release (M5), code decides and docs follow — when the implementation
forces a change, update the doc in the same task. After M5 the direction
inverts: docs are the contract.

## 1. Environment

- **Python 3.13**, managed by **uv** (single repo, uv workspace; one wheel per
  directory under `packages/`, dist name `tutelary-<sub>` ↔ import
  `tutelary.<sub>`).
- Lint/format: **ruff**. Style is whatever ruff says — if a rule fights the
  code, change the config deliberately; never silence a rule inline without a
  written reason.
- Tests: **pytest** (asyncio in auto mode).

```bash
uv sync --all-packages                  # set up / update the environment
uv run ruff check .                     # lint
uv run ruff format .                    # format
uv run pytest                           # all tests
uv run pytest packages/core/tests -q    # one package's tests
```

Dependencies go in the owning package's `pyproject.toml`
(`uv add --package tutelary-context <dep>`). `packages/core` stays
dependency-free — always, no exceptions.

## 2. Git Policy (Hard Rule)

**Commits and pushes are executed by the user, not by you.**

- Never run `git commit` or `git push` on your own initiative. Leave the
  working tree for the user to commit; don't stage on their behalf.
- When a task or phase completes, report the change list and test results,
  then let the user decide about committing.
- The only exception: an explicit, task-specific instruction in the current
  conversation ("commit this now") — scope-locked to that instruction.
- No force-push, no history rewriting, no tag creation without explicit
  instruction.

## 3. Behavioral Guidelines

### 3.1 Think Before Coding

Don't assume. Don't hide confusion. Surface tradeoffs.

- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 3.2 Simplicity First

Minimum code that solves the problem. Nothing speculative.

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes,
simplify. (For this repo also ask: "Does the kernel need this, or does the
component?" Shared vocabulary goes in core; single-consumer logic stays in
the component.)

### 3.3 Surgical Changes

Touch only what you must. Clean up only your own mess.

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it — don't delete it.
- Remove imports/variables/functions that *your* change made unused; leave
  pre-existing dead code unless asked.

The test: every changed line traces directly to the current task.

### 3.4 Goal-Driven Execution

Define success criteria. Loop until verified.

- "Add validation" → write the failing test for invalid input, then make it
  pass.
- "Fix a bug" → write the regression test that reproduces it, then make it
  pass.
- "Refactor X" → tests green before and after.

For multi-step tasks, state a brief plan first:

1. [step] → verify: [check]
2. [step] → verify: [check]

For framework work, the success criteria are usually concrete and already
defined: the component's `examples/only-*.py` running offline, its contract
checks, and the architecture tests. Aim at those; they are the definition of
"works", not an afterthought.

## 4. Quality & Readability Constraints

These bound **how** code is written — never **what** gets built. Feature
design, scope, and priorities are not constrained by this section.

1. **Never disable the judges.** `tests/architecture`, the contract suites,
   and `examples/only-*` are the project's design verdicts. If one blocks
   you, that is a design signal: stop and surface it. Never delete, skip,
   or xfail a guard test to make progress.
2. **Dependency direction is law.** Components import only `tutelary.core`
   and themselves; zero horizontal imports between components; `core`
   imports nothing outside the stdlib. Cross-component cooperation goes
   through Bus events or port injection — nothing else.
3. **Typed boundaries.** Public APIs carry full type annotations and stay
   pyright-clean. Data crossing a package boundary is a frozen dataclass or
   a pydantic model — never a bare `dict[str, Any]`.
4. **Async discipline.** No blocking calls inside the event loop (sync file
   IO, `time.sleep`, sync HTTP); every IO gets a timeout; never swallow
   `asyncio.CancelledError` — let it propagate.
5. **Errors are typed.** Raise the specific error types defined in core (or
   introduce a new typed error via a doc update); catch only what you
   expect; no bare `except:`; no catch-log-reraise chains that add nothing.
6. **Standalone usability is the test of decoupling.** If a component's
   `only-*` example can't be written or fails, fix the coupling — not the
   example.
7. **Tests mirror code.** Unit tests live in `packages/<pkg>/tests/`, named
   after the module they exercise. Unit tests use the core fakes — no
   network, no real LLM, no Docker (docker-marked integration tests are a
   separate lane).
8. **Code carries comments; comments carry "why".** Every public API gets a
   docstring (what it does, its contract, side effects); inline comments
   explain constraints, tradeoffs, and pitfalls the code cannot show. No
   narration, no history/issue references, no commented-out code.
9. **Readable units.** Prefer functions a reader can hold in their head.
   Split when a second reason to change appears — never by line count.
10. **Language.** Code, identifiers, and commit messages are English; code
    comments (including docstrings) are written in Chinese, kept
    standardized: complete sentences, consistent punctuation, technical
    terms may stay in English where that is clearer. The design docs in
    `docs/` are currently Chinese — when updating them, match each file's
    existing language.

## 5. Definition of Done (per coding task)

- [ ] `uv run ruff check .` and `uv run ruff format .` clean
- [ ] `uv run pytest` green for touched packages, including
      `tests/architecture`
- [ ] New behavior has tests; bug fixes have a regression test
- [ ] Docs updated in the same task if contracts/structure changed
      (`03`/`04`/`08`) or phase status moved (`09`)
- [ ] No commit made — changes reported to the user for review

These guidelines are working if diffs stay minimal, overcomplication is
rewritten before review, clarifying questions come before implementation,
and the guard tests never need to fire.
