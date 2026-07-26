# Handoff — write-guard reachability plan IMPLEMENTED (2026-07-25/26)

Successor to `2026-07-24-write-guard-allowlist-and-claudemd-audit.md` (832 lines, the planning
arc). That file is history — do not edit it. This one covers implementation.

**Branch:** `fix/write-guard-plan-allowlist` · **Tip at write time:** `6aca97d`
**Baseline:** `python3 -m pytest hooks/tests/ --ignore=hooks/tests/test_prompt_dispatcher.py -q`
→ **1002 passed, 0 failed, 9 skipped**. `python3 -m ruff check .` clean. Both verified by the
orchestrator, not taken from an agent report.

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

Plan file `docs/plans/2026-07-25-write-guard-reachability.md` is **gitignored** and stays at
`status: planned`. **Do NOT flip it.** The gate had to stay dormant to edit the code implementing
it, and the allowlist that would authorize those edits still does not exist.

---

## IN FLIGHT — agent `wg-task2` is working these three right now

From the Codex re-review (no P1s; the fixes hold). All three verified by the orchestrator. If the
agent is gone, re-dispatch from this section — it is complete.

**F1 [P2] `hooks/tests/test_write_guard.py:930-951` — git-env test covers the wrong variables.**
It sets `GIT_DIR`/`GIT_WORK_TREE`, the two that never bypassed anything. Zero coverage for
`GIT_COMMON_DIR`, `GIT_CEILING_DIRECTORIES`, or unknown-`GIT_*` default-deny. Add all three
(invented var e.g. `GIT_TOTALLY_MADE_UP` locks fail-closed); each asserts block, excludes
`HOOK CRASH`, requires the Phase-5 reason.

**F2 [P3] `test_write_guard.py:615` — the ambiguous-`.paul` test cannot fail.** Its assertions sit
inside `if parsed is not None and parsed.get("decision") == "block":`, so a silent allow (what
removing `check_paul_phase_gate` produces) skips every assertion. Assert positively. Expected
reason, reproduced scrubbed: `BLOCKED: PAUL phase '03-x' isn't assumed — ASSUMPTIONS.md is missing`.
**Fix the Task 1 sibling too** — `test_paul_artifact_is_NOT_blocked_by_an_armed_plan` has the
identical shape (different expected PAUL reason; assert each one's actual reason).

**F3 [P3] `hooks/write-guard.py:133` — `return "tmp"` is dead production code.** `check_phase5`
returns early on `plan_root is None` and otherwise always passes non-`None`, so the guard always
fires. Preference: DELETE the `/tmp` branch; its only production effect duplicates the fallthrough,
and leaving it invites restoring the exemption. Check `TestOrchestratorExemptionCategory`'s
`plan_root=None` spelling tests — delete any made meaningless rather than keeping the branch alive
to satisfy them. Then update `phases/execution.md:22` + docstring: `/tmp` is no longer an exemption
root at all.

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
