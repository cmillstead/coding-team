# Handoff — coding-team fast-lane (process-weight) fix

**Date:** 2026-06-14 · **Branch:** `coding-team-weight-asymmetry-fastlane` (off `codex-learnings-c13-c15`)
**Repo:** `/Users/cevin/.claude/skills/coding-team`

## What this is
Fixing coding-team's process-weight slowness. Two batches:
- **Batch 1 — hook hot-path latency** (the real felt win, esp. builder-self-check ~55s/edit).
- **Batch 2 — instruction-file weight asymmetry**: introduce ONE quantified task-weight ladder (`phases/task-weight.md`) referenced by every gate, so trivial tasks pay trivial ceremony.

Diagnosis & 36 findings: `docs/weight-asymmetry-audit-2026-06-14.md` (the audit brief).
Implementation plan: `docs/plans/2026-06-14-coding-team-fastlane.md` (23 task headers; real tasks = 1,3,4,4b,5,6,7gate + 8–21; Task 2 REMOVED).

## Gate status
Plan passed through **11 Codex (`/second-opinion review`) rounds**; every round found real defects (zero false positives). Iteration 12 (final) landed: precise PostToolUse note + single end-of-execution effective-tier recompute. **User directed: proceed to execution without a final PASS** — remaining items were refinements, not breakage. Codex prompt saved at `/tmp/codex-fastlane-prompt.txt` (may be cleared; reconstruct from the plan's review focus if needed).

## CRITICAL execution decisions (do not relitigate)
1. **Execute with the plan at `status: planned` — NOT in-progress.** write-guard.py blocks edits to instruction `.md` AND any `hooks/*.py|*.sh` only when a plan is `status: in-progress`. This plan edits those very files, so flipping it in-progress self-deadlocks (escape needs a session-level env var that can't be set mid-session). Keeping it `planned` keeps write-guard disarmed. Orchestrator enforces planned scope manually and runs completion gates manually. **Do not flip to in-progress.**
2. **Finding 32 (git-safety-guard latency) = FALSE POSITIVE**, Task 2 removed. Its git subprocesses are already commit-gated; no per-edit cost. Handler left untouched. (Separate out-of-scope NOTE: its PostToolUse exit-code handler is registered nowhere → exit-code commit gate is dormant. Pre-existing; NOT fixed here.)
3. **qmd is obsolete** — user uses engram, hasn't used qmd in months. Task 6 REMOVES the `qmd-vault-embed.sh` hook entirely (source + test + settings.json registration + deployed symlink) AND removes the qmd probe from `hook-health-check.py:check_mcp_health()` + its test. Scope guard: do NOT touch the qmd MCP server or CLAUDE.md memory docs.
4. **Risk classifier** is SEMANTIC (by effect, not filename — filenames are hints), a 7-class SUPERSET of every high-stakes category the harness recognizes (security/trust-boundary, payment/billing, data-deletion/destructive, public-contract, schema/data, dependency, instruction-file). Tier = max(size-tier, risk-tier). **Effective tier ratchets UP only**: recomputed ONCE at the top of the end-of-execution gate sequence (before QA at execution.md:151), consumed by all end gates (QA/doc-drift/verification/post-exec/Phase-6).

## Progress
- [x] Branch hygiene: committed in-flight codex-learnings work (`e7222ef`), cut clean branch, committed audit brief (`a328102`).
- [x] Plan written + 11 Codex rounds + iteration 12 final.
- [x] **Task 1 (builder-self-check off hot path) — DONE, commit `eb00d3d`.** Fire-and-forget `_spawn_background_worker`/`_run_worker` (`--worker` mode), findings deferred to LOG_FILE. Tests green, deployed, symlink verified.
- [x] **Discussion checkpoint 2026-06-14:** user confirmed proceed-as-planned, no scope change. Plan remains `status: planned`.
- [x] **BATCH 1 COMPLETE (2026-06-14).** Commits: Task 3 `03b514d`, Task 4 `e919a13`, Task 4b `9c2b843`, Task 5 `232f9c4`, Task 6 `6485dc9`. All deployed; symlinks verified to repo source; qmd fully retired (settings.json + symlink + source greps all 0). Safety gate `test_in_place_status_flip_is_seen_immediately` passes (cache never leaves write-guard disarmed).
- [x] **Task 7 gate GREEN.** Full suite: 554 passed, 8 skipped, **10 pre-existing failures** (7 `TestSkillEvalHarness::test_skill_routing`, 2 `TestMigrationGuard`, 1 `test_ignores_internal_hooks`) — independently confirmed pre-existing by reproducing all 10 identically at baseline `e919a13` (before any write-guard change). Zero Batch 1 regressions. Deploy "All hooks registered." + deploy parity verified on all 6 modified artifacts.

## Remaining work (in order)
**Batch 1 (each task = full text in the plan; dispatch a sonnet `Coding Team Implementer`, give full task text, do NOT make it read the plan):**
- [x] Task 3 — loop-detection.py conditional save_state. `03b514d`.
- [x] Task 4 — hook-health-check.py non-blocking `get_pr_throughput` + 1h cache. `e919a13`.
- [x] Task 4b — `_lib/state.py:get_session_id()` prefers `CLAUDE_CODE_SESSION_ID` + health-check uses shared helper. `9c2b843`.
- [x] Task 5 — `_lib/active_plan.py` cross-invocation file cache, wired into write-guard.py + coding-team-lifecycle.py. In-place flip safety test passes. `232f9c4`.
- [x] Task 6 — REMOVED qmd-vault-embed (hook + test + settings.json + symlink + health-probe). `6485dc9`.
- [x] Task 7 (gate) — GREEN. 554 passed / 10 pre-existing failures (confirmed at baseline e919a13) / deploy parity verified / qmd source greps == 0.

**Shared-file sequencing (MANDATORY — no parallel on same file):** `hook-health-check.py` is touched by Task 4 (get_pr_throughput) → 4b (session-id :502) → 6 (qmd probe), different functions — run sequentially in that order. Task 5 after 4b. Task 1 & Task 3 are independent (could parallelize).

**Batch 2 (Tasks 8–21): COMPLETE (2026-06-14).** On branch `coding-team-weight-ladder-batch2` (cut off Batch 1 tip `fe2bfd4`; stacks on PR #73). 15 commits, instruction-files only (zero code → Batch 1 hook suite unaffected). Commits: Task 8 ladder primitive `c0d81fb`; Task 9 SKILL.md `4b5bfcf`; Task 9a single effective-tier recompute `300762c`; Task 11 `e688a94`; Task 16 `47c8f21`; Task 17 `7b7cb78`; Task 15 `ad69be6`; Task 20 `3a1e145`; Task 10 `9e5fc88`; Task 13 `e3ff00c`; Task 14 `71dfa08`; Task 12 `b3e0b0c`; Task 18 `49b15dc`; Task 19 `5ca1b2e`; Task 21 fix `3055938`.
- **Task 21 gate GREEN.** Mechanical greps: ladder table only in task-weight.md (DRY); no unscoped bypass; no `1 task AND ≤3 files` as a skip test (only Small-boundary docs); no grep-style risk scan; deploy "All hooks registered." Opus prompt-craft audit: Sections A–F all PASS (gate-matrix conformance, single recompute before QA, 7-class semantic risk, equal-force, no multi-edit contradictions, structure <200 lines). One P3 nit (task-weight.md:72 self-description) fixed in `3055938`.
- **Phase 6 verification:** instruction-only diff (vs `fe2bfd4`) → code suite (554 passed) unaffected; no doc-drift in README/CLAUDE.md; deploy clean. Plan left `status: planned` (never in-progress). Unrelated WIP (`skills/second-opinion/codex-learnings.md`, `memory/patterns.md`) restored untouched.

**NEXT (not started): land Batch 2.** Branch is NOT yet pushed/PR'd. Because it stacks on Batch 1, the Batch 2 PR should target the Batch 1 branch `coding-team-weight-asymmetry-fastlane` (PR #73's head) — so the PR diff shows only the 18 instruction files. After PR #73 merges to main, rebase Batch 2 onto main. Optional: post-exec Codex `/second-opinion review` on the instruction diff (offered, not required — the opus audit already validated conformance).

## Resume procedure
1. `cd /Users/cevin/.claude/skills/coding-team && git status && git log --oneline -5` (confirm on branch, see committed tasks).
2. Read this handoff + the plan. Grep the plan for `### Task N` to get the next undone task's full text.
3. Continue Batch 1 at Task 3, respecting shared-file sequencing above.
4. Keep `status: planned` throughout. Do NOT spawn more Codex rounds unless a new design question arises.
