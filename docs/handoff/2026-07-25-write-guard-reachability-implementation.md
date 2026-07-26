# Handoff — write-guard reachability plan IMPLEMENTED (2026-07-25/26)

Successor to `2026-07-24-write-guard-allowlist-and-claudemd-audit.md` (832 lines, the planning
arc). That file is history — do not edit it. This one covers implementation.

**Branch:** `fix/write-guard-plan-allowlist` · **Tip at last update:** `b10d80a`
**Baseline:** `python3 -m pytest hooks/tests/ --ignore=hooks/tests/test_prompt_dispatcher.py -q`
→ **1003 passed, 0 failed, 9 skipped**. `python3 -m ruff check .` clean. Live hook probed healthy.
All verified by the orchestrator, not taken from an agent report.

**Working tree:** clean except two PRE-EXISTING, not-ours files — `.claude/settings.local.json`
(modified) and an untracked `skills/second-opinion/codex-learnings.d/2026072 3-...-self-heal-...md`.
Never stage either.

---

## What landed

| Commit | Content |
|---|---|
| `4d932f4` | Task 1 — orchestrator-exemption bypass; structural path matching, per-root conditional exemptions |
| `51f0734` | Task 4 — documented cwd-relocation bypass removed from `phases/` + 3 copies in the gitignored fastlane plan |
| `d618597` | Step 0 — `RuntimeError` in `_plan_repo_root` (function later removed as redundant) |
| `a60dbd6` | Task 2 — target-scoped git identity; the gate follows the FILE, not the process |
| `3de91e4` | Task 3 — never cache a negative active-plan result |
| `14d1a50`, `851dc73` | doc-drift: stale line citations → symbol/section anchors |
| `fce95de` | `"I'm only finishing my own in-flight refactor"` rationalization + `docs/tickets/2026-07-25-self-modifying-hook-no-safe-edit-path.md` |
| `6aca97d` | Review fix batch — all 9 QA/Codex findings |
| `d25a241` | this handoff |
| `b10d80a` | Codex re-review F1/F2/F3 — git-env test coverage, crash-vacuous PAUL tests, dead `/tmp` branch deleted |

Plan file `docs/plans/2026-07-25-write-guard-reachability.md` is **gitignored** and stays at
`status: planned`. **Do NOT flip it.** The gate had to stay dormant to edit the code implementing
it, and the allowlist that would authorize those edits still does not exist.

---

## Codex re-review (no P1s) — F1/F2/F3 LANDED in `b10d80a`, verified

All three accepted only after independent orchestrator verification, not from the agent report:

- **F1** — `test_git_env_vars_cannot_redirect_the_root` is now parametrized over 4 cases:
  `GIT_DIR`+`GIT_WORK_TREE`, `GIT_COMMON_DIR`, `GIT_CEILING_DIRECTORIES`, and
  `GIT_TOTALLY_MADE_UP` (locks the allowlist's default-deny direction). All route through
  `_assert_blocked_by_phase5`.
- **F2** — both PAUL tests assert UNCONDITIONALLY now, exclude `HOOK CRASH`, exclude the *wrong*
  gate's reason, and positively require `check_paul_phase_gate`'s own
  `PAUL phase '03-x' isn't assumed`. `grep "if parsed is not None and parsed"` returns zero hits.
- **F3** — the `/tmp` branch plus `_TMP_ROOT`/`_TMP_ROOT_RESOLVED`/`_tmp_root_resolved()` deleted.
  Safety premise re-verified independently: `_orchestrator_exemption_category` has exactly ONE
  production call site (`write-guard.py:279`), guarded by the `plan_root is None` early return
  above it — the branch was genuinely unreachable. The end-to-end P1-A lock
  `test_linked_worktree_under_real_tmp_is_not_exempted` SURVIVES; only unit tests covering the
  retired containment framing were dropped. Probed scrubbed: an unowned `/tmp` instruction file
  still allows (no regression).

`hooks/tests/conftest.py`'s task-#12 root-cause docstring was also corrected (it described the
now-deleted exemption as a live mechanism). Docstring-only — `config.addinivalue_line` untouched.

## IN FLIGHT — agent `wg-drift`, two P3 doc-drift residues F3's sweep missed

Comments and markdown ONLY; behavior is settled and must not change. Re-dispatch from here if lost.

**V1 `SKILL.md:181`** — the Phase 5 Edit Routing table still lists `/tmp/*` as "Orchestrator edits
directly", unqualified. `phases/execution.md:22` was updated and explicitly defers to this table
("See 'Phase 5 Edit Routing' in SKILL.md"), so the authority and the prose now disagree — and
unqualified `/tmp` describes the P1-A bypass shape (linked worktree under `/tmp` inside an armed
repo) as permitted policy. Same row's `memory/*.md` cell is likewise missing execution.md:22's
instruction-file qualifier.

**V2 `hooks/write-guard.py` `~:256`, `~:274`, `~:300`** — three comments inside `check_phase5` still
describe `/tmp` as a live conditional exemption. `:274` claims `memory/` and `/tmp` "are
re-evaluated below"; nothing re-evaluates `/tmp`. `:300`'s conclusion ("only memory needs the
conjunction") is right but its stated reason is now false. Re-ground, don't just delete — these sit
in the very function a future reader would "restore" the branch from, which the F3 docstring names
as how P1-A came to exist.

---

## Non-negotiables (each cost a round to learn)

1. **Never flip a plan to `status: in-progress`** during this work.
2. **Scrub the override on EVERY gate probe.** This session exports
   `WRITE_GUARD_ALLOW_INSTRUCTION_EDIT=1`; it corrupted a Codex probe into a false clear.
   `env -u WRITE_GUARD_ALLOW_INSTRUCTION_EDIT -u CODING_TEAM_MAIN_ROOT -u CODING_TEAM_TEST_SEAM`.
   Confirm `echo "[${WRITE_GUARD_ALLOW_INSTRUCTION_EDIT}]"` prints `[]`. An unscrubbed *allow* is
   worthless evidence; an *unscrubbed block* still counts. Always pair with a control that must block.
3. **Editing `hooks/write-guard.py` or `hooks/_lib/*` can wedge the session editing it** — the live
   hook imports them; a crash blocks ALL Edit/Write for every agent at once, and
   `WRITE_GUARD_ALLOW_INSTRUCTION_EDIT` cannot recover it (read AFTER the crash point). One
   self-consistent edit at a time; after each, run BOTH `python3 -c "import sys;
   sys.path.insert(0,'hooks'); import _lib.active_plan"` AND a live-hook probe — **import alone is
   insufficient**, it passed while wedged (stale name inside a function body, raised only at call
   time). If wedged: STOP and report. Do NOT repair via Bash. The orchestrator did once, only with
   explicit user authorization; that authorization is the distinguishing fact.
4. **The exemption list is HETEROGENEOUS** — never collapse it into one uniform rule.
5. Explicit paths on every commit. Never `git add -A`.
6. Every block assertion excludes `HOOK CRASH` + requires a gate-specific reason. A *conditional*
   assertion block is a vacuity hole (F2).

---

## What the gate now does (all reproduced scrubbed, fixtures cleaned up)

| Case | Result |
|---|---|
| Instruction file, armed plan, ordinary checkout | block |
| Linked worktree under literal `/tmp`, armed main checkout | block (was **allow** — the P1) |
| `GIT_COMMON_DIR` → empty repo | block (was **allow**) |
| `GIT_CEILING_DIRECTORIES` → armed root | block (was **allow**) |
| `.paul` artifact + two armed plans | block **by the PAUL gate's own reason** (was ambiguity block → gate unreachable) |
| Non-exempt file, same ambiguous state | ambiguity block (scope preserved) |
| Unowned `/tmp` scratch, no repo | allow (no regression) |
| Relative `file_path` | dormant — no longer cwd-scoped |

---

## Memories written this session

`feedback-self-modifying-hook-wedge`, `feedback-ambient-env-corrupts-verification` (both in
`memory/`, indexed in `MEMORY.md`). Codex learning **C28** was written during planning.

---

## After this plan

Task #2 — the plan-scoped allowlist (`docs/plans/2026-07-24-write-guard-plan-allowlist.md`, 1507
lines, gitignored) — **unblocks**. Per-file authorization is finally meaningful now the gate cannot
be bypassed wholesale. It carries deferred items: P1-3 duplicate frontmatter keys, P2-7
`RuntimeError`/ELOOP + non-branch-specific `_assert_blocked`, P1-2 worktree declaration matching,
and the stale-POSITIVE cache misidentification (recorded at `_lib/active_plan.py` ~`:375-382`).

Also queued: #1 spec-silence meta-rule (paused, its Codex plan gate never ran), #3 CLAUDE.md audit
Batch 1, #4 `commands/` not in `deploy.sh` (stale `/build` + 5 undeployed commands).

Open decision: the hazard ticket at `docs/tickets/2026-07-25-self-modifying-hook-no-safe-edit-path.md`
lists four options and picks none. Needs a human call.
