# Write-guard plan-scoped allowlist — COMPLETE (2026-07-26)

Supersedes `2026-07-26-write-guard-allowlist-tasks-1-2.md`. Plan
`docs/plans/2026-07-24-write-guard-plan-allowlist.md` is `status: complete`.
Do not reopen it.

**Branch:** `fix/write-guard-plan-allowlist` · **Tip:** `64a5861` · not yet pushed.

| Commit | Content |
|---|---|
| `b20a374` | Task 1 — allowlist reader in `_lib/active_plan.py` |
| `a4fc422` | duplicate-key error names the offending plan |
| `e970cbb` | Task 2 — allowlist wired into `check_phase5()` |
| `7960e31` | Task 3 — 14-test adversarial/fail-closed battery |
| `5e1d181` | Task 4 — routing docs |
| `64a5861` | Task 4 fix — restore Agent-tool routing alongside authorization |

**Final state, orchestrator-verified (not taken from agent reports):** 1039
passed / 9 skipped (`hooks/tests/`, excluding `test_prompt_dispatcher.py`),
`ruff check .` clean, `SKILL.md` 198/200. End-to-end proof run against BOTH
`hooks/write-guard.py` and the deployed `~/.claude/hooks/write-guard.py`:
declared file allowed, undeclared blocked, `hatch=[]` on every probe.

Tasks 3–5 dogfooded the feature: the plan declared its own 8 files and every
edit ran through the live gate. Gate confirmed dormant after close-out
(`phases/execution.md` allows again; no plan left `in-progress`).

## Two decisions made during this session

1. **`phases/task-weight.md:35` fixed** (was flagged as an open GAP). Its
   "`BEHAVIORAL_INSTRUCTION_DIRS` always-delegates" clause stopped being true
   once a declared file is allowed. Declared up front so Task 4 would not wedge
   on it. Medium-minimum tiering conclusion untouched — accuracy only.
2. **A third stale remediation list found and fixed.** The plan's Step 4a named
   two (`execution.md:39`, `named-rationalizations.md:68`);
   `named-rationalizations.md:38` carried the identical three-route list and is
   now updated too.

## The one real defect, and where it came from

`5e1d181` deleted the Agent-tool *routing* requirement in four places instead
of adding the *authorization* requirement beside it, leaving
`phases/execution.md:22` contradicting `:39` in the same file. Tests, line cap,
and the verification grep all passed — it was visible only by reading the prose.

The defective table row came from **the plan's own spec text at `:1607`**, which
supplied a verbatim replacement omitting the routing half; the implementer
complied exactly. Fixed in `64a5861`. Lesson recorded as the
`feedback-insufficient-is-not-wrong` memory: when a rule becomes
necessary-but-not-sufficient, brief it as "must state BOTH X AND Y", never as
"drop the claim that X".

## Known gaps — deliberately NOT closed, each needs its own plan

Recorded so they are not silently dropped (`rules/finding-integrity.md`):

1. **Ungated symlink alias** — `is_instruction_file()` classifies the lexical
   payload path, so `notes/x.txt` → `agents/X.md` is not gated.
2. **Case-insensitive filesystem** — on APFS `skills/demo/skill.md` reaches the
   gated `SKILL.md` without matching the case-sensitive basename set.
3. **Frontmatter beyond the 4096-char window**, and an unterminated frontmatter
   block, both make discovery return no plan — silently disarming the gate.
4. **General stale-POSITIVE cache hole** — only its *authorization* consequence
   was closed (D1's uncached re-check). Window is narrow: needs an
   mtime-preserving status change.

## Also worth knowing

- **codesight is mispointed for this repo** — rejects the path as outside its
  trusted `/Users/cevin/src/` prefix, and its "coding-team" index returns ZERO
  results for classes that demonstrably exist. Agents fell back to Grep/Read
  correctly, but an index returning *empty* rather than *erroring* reads as "no
  callers found" and gets trusted. Re-point before an audit leans on it.
- `docs/plans/2026-07-25-write-guard-reachability.md` was still `status: planned`
  despite being complete; corrected to `complete` this session.
- Working tree carries two pre-existing not-ours files —
  `.claude/settings.local.json` (modified) and an untracked file under
  `skills/second-opinion/codex-learnings.d/`. Never stage either.

## Queue

#1 spec-silence meta-rule (paused; its plan now carries the first real
`instruction_files:` declaration and is ready to run), #3 CLAUDE.md audit
Batch 1, #4 `commands/` not in `deploy.sh` (stale `/build` + 5 undeployed
commands).

Open decision, still unanswered:
`docs/tickets/2026-07-25-self-modifying-hook-no-safe-edit-path.md` lists four
options and picks none. Needs a human call.
