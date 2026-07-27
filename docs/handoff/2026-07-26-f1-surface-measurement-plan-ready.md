# Handoff — F1 surface-measurement plan READY, execution not started (2026-07-26)

Supersedes nothing. Companion to `2026-07-26-saturation-remediation-phase1-complete.md`,
which is still accurate for everything outside this plan. Every state claim below
was verified by command at write time.

## Where this stopped and why

Phase 4 is COMPLETE — the plan is written and survived two full review rounds.
Execution has NOT started. I stopped at the Codex plan gate because the remaining
work (25 learning-entry deep-checks + Codex dispatch + 4 implementer tasks +
Phase 5/6 exit gates) does not fit in the session's remaining context.

**Nothing is half-applied. No code has changed. The repo is clean.**

## Repo state

- **Branch:** `feat/always-loaded-surface-measurement`, cut from synced `main` @ `0998201`. Zero commits on it.
- **`main`** @ `0998201`. Merged today: #118–#124.
- **No plan is `status: in-progress`** — `write-guard.py` is DORMANT. If a future
  session finds instruction edits blocked, hunt for a stale `in-progress` plan
  before reaching for `WRITE_GUARD_ALLOW_INSTRUCTION_EDIT`. Never set it.
- **Working tree carries two pre-existing not-ours files** — `.claude/settings.local.json`
  (modified) and untracked `skills/second-opinion/codex-learnings.d/20260723-...-self-heal-migration-schema-shape.md`.
  **Never stage either.** The second is a live C27 learning entry AND the cause of
  the digest test failure (see "Known failures").
- **Verified baseline:** `python3 -m pytest hooks/tests -q` → **1055 passed, 9 skipped**.
  `ruff check .` → clean. I ran this myself; it is not carried from a brief.

## The plan

`docs/plans/2026-07-26-always-loaded-surface-measurement.md` — **1028 lines,
`status: planned`, gitignored** (`.gitignore:2`, so it will never be committed).

```yaml
instruction_files: hooks/hook-health-check.py, hooks/tests/test_hook_health_check.py
```

Both reviewers independently confirmed this declaration is complete AND minimal.
`docs/*` is not gated; `scripts/deploy.sh` is executed, not edited.

**Task order — 4 tasks, do not reorder:**

| # | Task | Model |
|---|---|---|
| 1 | `check_always_loaded_surface()` + `_count_lines()` + tests, 7-row mutation table | sonnet |
| 2 | Wire into `main()`, extend integration allowlist, live probe, `deploy.sh` | sonnet |
| 3 | Correct F3's prescription + 2 Appendix B prediction rows in the audit report | sonnet |
| 4 | Update the handoff's stale F1 entry and symlink counts | haiku |

**Task 1 Step 0 captures `BASELINE` first.** Later totals are `BASELINE + 8` and
`BASELINE + 9` — with the measured 1055 that is 1063 / 1064. Do not reintroduce
absolute numbers.

## What the fix is, and why this shape

`hooks/hook-health-check.py:186-190` globs `agents/*.md`, `phases/*.md`,
`skills/*/SKILL.md` against `repo_root = Path(__file__).parent.parent` (`:184`),
per-file threshold 200 at `:196`. All repo-rooted, so `config/CLAUDE.md` (238) and
`rules/*.md` are never measured.

The fix adds an **aggregate** check of the **deployed** surface —
`~/.claude/CLAUDE.md` + `~/.claude/rules/*.md`, summed. Reading the deployed
directory is the whole point: `~/.claude/rules/` is written by two repos
(2 symlinks from here, 5 regular files owned by the parent `claude-harness`), so
the deployed tree spans both owners by construction and the ownership question
does not need resolving for the measurement to be right.

**The audit's own F1 prescription was rejected in the plan** — adding `config/*.md`
+ `rules/*.md` to the existing glob list would measure 61 lines instead of 354, a
falsely reassuring number, and a per-file threshold never fires on 5-29-line rules.

Current surface: **354** = `~/.claude/CLAUDE.md` 238 + `~/.claude/rules/` 116.

**This is a WARNING, never a block.** It fires immediately at 354 and that is
intended. A blocking cap is audit finding **F2, which must land LAST**, after the
reductions — at 238 lines a cap that blocks >200 would block the very edits that
reduce it. The plan carries a dedicated "this is NOT F2" comparison table.

## Resume from here

1. **Finish the Codex plan gate** (Medium tier ⇒ REQUIRED; `codex` IS installed).
   Pre-flight is already computed and reproduced below — you can start from it
   rather than re-deriving, but re-verify the live count first (`ls` the
   drop-folder; it was 32).

```
mode: plan
signals: metric-aggregate(2), command-grammar(9)
dismissed(7): C24,C23,C2,C3,C5 N/A(scope-mismatch:diff vs mode:plan)
              C17 N/A(no-signal:path-equality, grep -c = 0)
              C12 N/A(no-signal:concurrency-lock, grep -c = 0)
applicable(25): P1,P2,P3,P4 (floor) · P30,P31,P32,P33 · C4,C10,C11,C13,C14,C15,
                C16,C18,C19,C20,C21,C22,C25,C26,C27,C28
total: 25 + 7 = 32   floor-note: C28 floored — its category `dual-resolution-policy`
                     is NOT in `_header.md`'s 19-value enum, so it reads as untagged
```

2. **Then Phase 5** — flip the plan to `status: in-progress` (this arms the
   write-guard against the two declared paths), dispatch Tasks 1-4 in order.
3. **Then the 4 blocking Phase 5 exit gates:** full-suite test+lint, `ct-qa-reviewer`,
   doc-drift scan, post-exec Codex `review`. All RUN at Medium.

## Hazards — read before touching anything

- **`~/.claude/hooks/hook-health-check.py` is a SYMLINK to the repo source.** Editing
  the source changes the live hook instantly. It runs at SessionStart, so a syntax
  error will not wedge the current session but WILL break the next one. Every task
  editing it must end with a live-hook probe; if the probe shows a regular copy
  instead of a symlink, STOP — do not hand-edit `~/.claude/hooks/`.
- **Known flake, not a regression:** `test_ci_orphan_detector.py::test_exits_cleanly_with_empty_input`
  shells out via `subprocess.run` and intermittently times out. Observed failing
  once and passing on immediate re-run this session. Re-run once before investigating.
- **Do not "helpfully" add `.resolve()`** while inside `hook-health-check.py` — see
  the discovery below. It is out of scope and would change the existing check's
  behavior mid-plan.

## Discovery this session — NOT in scope, deserves its own phase

**`Path(__file__)` is not symlink-resolved, so `repo_root` differs between the
deployed hook and the test suite.**

- Deployed (SessionStart banner): `agents/ct-implementer.md` 206, `skills/firecrawl/SKILL.md` 253, `skills/review/SKILL.md` 1467 — the last two do not exist in this repo.
- Under pytest: `phases/execution.md` 218, `agents/ct-implementer.md` 206, `phases/planning.md` 202.

Because `~/.claude/hooks/hook-health-check.py` is a symlink, `repo_root` evaluates
to `~/.claude` in production and to the coding-team repo under test. The existing
per-file instruction-length check has therefore been reporting on deployed
`~/.claude/agents/` and `~/.claude/skills/` all along, not on the repo its globs
were written for. Same root cause as F1 wearing a different hat.

It does not affect this plan — the new check reads `Path.home() / ".claude"`
explicitly and never touches `__file__`. Recorded in the plan's NOT-in-scope.

**This is also load-bearing for a plan gate:** it is *why* Task 2 Step 3's
early-return change cannot be tested. `check_instruction_file_lengths()` is
repo-rooted and unconditionally non-empty (3 files >200), so `main()` never
reaches the early return under test. The plan documents that as an **honest
coverage gap, verified by inspection only** — Failure Modes row at `:966`. Do not
"fix" it by stubbing; that breaches the no-mocks invariant, and the elaborate
real-file alternative was considered and rejected on GP#17.

## Review history — 20 findings, all closed

- **Round 1** (12: 2 P1, 2 P2, 8 P3). Headline: a Failure Modes row claiming
  `Tested? Yes` for a regression no test could observe — all seven aggregate tests
  pass `claude_dir=` explicitly and are blind to the default.
- **Round 2** (8: 1 P1, 7 P3), by a FRESH reviewer that traced every branch of
  `main()`. Headline P1: the mutation table added to fix round 1 contained a row
  that could not fire — **the same defect class recurring inside its own fix.**
- All 20 addressed with no false-positive claims. Both P1s were confirmed by me
  independently, by command, before routing them back.

## Still open from the prior handoff (unchanged, none started)

1. Two-repo ownership of `~/.claude/rules/` — measurement is what this plan fixes;
   the ownership swap (2 coding-team-specific rules sit parent-owned, 2 generic
   rules sit coding-team-owned) is deferred and optional.
2. **PR #95** — audit says close it, re-land only its rule 2 as ~4 lines, AFTER
   Groups B-D.
3. **Groups B/C/D** — target 354 → 163. **F2 lands LAST.**
4. `~/.claude` branch `harness/reconcile-reference-deploy` @ `cbb8ea2` — **local,
   unpushed**, on top of 5 unpushed harness-map commits. Branched from HEAD, not
   `origin/main`, because `origin/main` there still carries
   `WRITE_GUARD_ALLOW_INSTRUCTION_EDIT: "1"` in `settings.json` — checking it out
   would disarm the write-guard gate in live config. Push from a `~/.claude`-rooted session.
5. `reference/` is not gated by write-guard — `BEHAVIORAL_INSTRUCTION_DIRS`
   (`hooks/write-guard.py:143-150`) omits both `rules` and `reference`.
6. Spec-silence meta-rule — `docs/plans/2026-07-24-spec-silence-meta-rule.md`,
   497 lines, `status: planned`, **31 tasks / 0 executed**, blocked on its Codex gate.
7. `commands/` not in `scripts/deploy.sh` — 22 files, zero matches.
8. Self-modifying hook ticket — `docs/tickets/2026-07-25-...md`, 4 options at
   `:46-54`, **needs the operator**, do not pick.
9. Digest test failure — `skills/second-opinion/scripts/test_build_digest.py::test_design_face_output_is_byte_identical_to_committed_digest`
   fails because the untracked `codex-learnings.d/20260723-...` entry renders into
   the generated digest but is absent from the committed one. Outside
   `pytest hooks/tests`, which is why the baseline reads green. **Operator decides:**
   commit the entry and regenerate, or delete it.

## Operating rules that earned their keep

1. **Dispatch agents WITHOUT `name` when you need the report inline.** Passing
   `name` silently forces background mode and overrides `run_in_background: false`.
2. **`SendMessage` resumes a completed agent from its transcript** and works well
   for revision rounds — used twice here. Latency ~75-90s; useless for steering a
   short task.
3. **Verify every agent state claim by command.** This session the planner
   corrected *me* on a fact I had asserted twice and already written into two
   documents. Agent file-CONTENT analysis is consistently excellent; agent claims
   about working-tree state are guesses. Reject the premise, keep the analysis.
4. **A fresh reviewer for round 2 was worth it** — it found the defect the revision
   introduced, which the original reviewer would have been primed to miss.
