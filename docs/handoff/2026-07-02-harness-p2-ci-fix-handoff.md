# Handoff: Harness P2 remediation — SHIPPED to PR #103, CI red on pre-existing tests

**Supersedes** `docs/handoff/2026-07-02-harness-remediation-p2-continuation.md` (the 3 P2 fixes it described are DONE + committed + pushed). Resume from THIS file.

Repo: `/Users/cevin/.claude/skills/coding-team` (the live coding-team skill). Branch: `fix/harness-audit-2026-07-02`.

## DONE this session (do NOT redo)
- **3 P2 fixes committed + pushed** under the "reference deployed harness files by absolute `~/.claude/...` path" convention (user-approved: Option 1 + a tracked follow-up):
  - `51653f1` **P2a** — 22 `commands/*.md` stubs (21 delegators + the `/build` alias) → absolute skill paths.
  - `2b152ef` **P2b** — 7 `agents/ct-*.md` files' `rules/` + `agents/reference/` + `skills/` refs → absolute; new `hooks/tests/test_agent_rule_refs.py` guard.
  - `d0131f6` **P2c** — `deploy.sh` target-aware orphan-agent-symlink prune + 4 tests (`test_deploy_symlinks.py`).
- Review round complete before commit: Codex (cross-model) REVISE→fixed, prompt-craft auditor, QA reviewer — all findings resolved (build.md straggler, README.md test gap, agents/reference stragglers, target-aware prune to avoid deleting a user's foreign `ct-*` symlink).
- **PR #103 open into `main`**: https://github.com/cmillstead/coding-team/pull/103 — NO merge (user reviews). PR body basis: `docs/reports/2026-07-02-harness-audit.md` + post-review fixes. Base carries `dffa7db` (paul-apply-review-gate tip, not yet in origin/main) — user accepted it lands too. Do NOT rebase/force-push/merge.
- Working plan/decision doc (untracked, docs/plans is gitignored): `docs/plans/2026-07-02-harness-p2-path-convention.md`.

## THE BLOCKER — CI red on PR #103 (pre-existing, NOT from the P2 work)
CI run 28636648756: both `test (3.11)` and `test (3.12)` FAIL. ~13 tests fail, all in `hooks/tests/test_write_guard.py` (`TestPhase5*` classes) + `hooks/tests/test_active_plan.py::TestCrossInvocationCache::test_block_decision_unchanged`. Every failure: expected `decision: block`, got `decision: allow` + reason "Identity framing missing … skill-files.md".

**Root cause (confirmed):** write-guard detects an active pipeline via `_lib/active_plan.py::find_active_plan()` → `_git_main_root()` → `git rev-parse --path-format=absolute --git-common-dir` (active_plan.py:81-96, stderr→DEVNULL, bare `except → None`). The Phase-5 tests build a tmp git repo, write an in-progress plan under `<tmp>/docs/plans/`, and run the hook with `cwd=<tmp repo>`. Locally `git rev-parse` succeeds in that tmp repo → plan found → block. On the ubuntu runner `_git_main_root()` returns `None` (git resolution fails silently in the ephemeral tmp repo) → no active plan → guard falls through to identity-framing advisory → `allow` → every "should block" test fails. Production is UNaffected (hook runs inside the user's real checkout where git works). **These tests are non-hermetic — they depend on `git rev-parse` succeeding in a pytest tmp repo on the runner.**

**CRITICAL — local suite is a FALSE GREEN:** `pytest tests/ -k "not llm_eval and not llm_judge"` reports 892 passed locally because THIS machine has an active coding-team session + working-copy plan state that makes the guard behave as "in pipeline." A green local run does NOT prove the CI fix. Verify the fix by SIMULATING the git failure locally (force `_git_main_root()` to None, or run with git unavailable) and confirming the tests still pass via the seam below.

## IN-FLIGHT FIX (implementer `cifix`, likely partial in the working tree)
`git status` will show uncommitted changes — at minimum `M hooks/_lib/active_plan.py`. The fix: add an OPT-IN, test-only env seam to `_git_main_root()` — if `CODING_TEAM_MAIN_ROOT` (or an existing convention if `grep -rn "MAIN_ROOT" hooks/` finds one) is set + non-empty, return `Path(that)` directly WITHOUT invoking git; when unset, behavior is byte-for-byte identical (production path unchanged). Then the failing tests (test_write_guard.py `repo` fixture / `_run` helper, and test_active_plan.py setup) set that env var to their tmp repo so they no longer depend on git. The seam in `_git_main_root()` covers BOTH `find_active_plan()` and `find_active_plan_cached()` (both call it).

**To resume:** run `git status`/`git diff` to inspect cifix's partial work.
- If complete + correct (seam is opt-in, tests updated, git-failure simulation proves CI-robustness, full suite green): review the diff, commit as `fix: hermetic active-plan resolution in write-guard tests via opt-in MAIN_ROOT seam (CI)`, push, then watch CI.
- If partial/absent: re-dispatch via `/coding-team` using the spec above (see the cifix brief in the prior session, or reconstruct from this section). Do NOT hand-edit `_lib/active_plan.py` directly — it's a shared hook lib; route through the Agent tool.

## REMAINING STEPS (in order)
1. Finish/verify the CI fix (above). Full hook suite green LOCALLY **and** git-failure-simulation proof.
2. Commit the CI fix + push to `fix/harness-audit-2026-07-02`.
3. Watch CI: `gh pr checks 103 --repo cmillstead/coding-team --watch`. Expect green.
4. **After CI green:** verify `stash@{0}` on `feat/paul-apply-review-gate` matches commit `6ada6b7` (content preserved there), then `git stash drop` it. Destructive — confirm with user first.
5. Tracked follow-up (NOT this PR): wire `commands/` into `deploy.sh` so the P2a stubs become the live commands + retire the 21 stale standalone `~/.claude/commands/*.md` copies (needs a per-command diff first). Documented in the PR body.

## Pre-existing, left untouched (flag, don't fix without user)
- Two plans in `docs/plans/` (`2026-06-14-coding-team-fastlane.md` status `planned`, `2026-06-20-coding-team-workflow-refactor-design.md` status `proposal`) — the earlier handoff mislabeled them "in-progress." Left as-is.
- `docs/plans` is gitignored (force-add if ever needed).

## Verify commands
- `git -C /Users/cevin/.claude/skills/coding-team log --oneline origin/main..HEAD`
- `cd hooks && python3 -m pytest tests/ -k "not llm_eval and not llm_judge" -q` (LOCAL false-green caveat above)
- `gh pr checks 103 --repo cmillstead/coding-team`
- deploy: `bash scripts/deploy.sh` (ends "All hooks registered." / "Deploy complete.")
