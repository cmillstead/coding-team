# Completion Summary — TRK-176 git-safety-guard checklist false-negative fix

**Shipped:** 2026-08-24 · PR #156 merged to `main` (merge commit `b662415`) · plan `docs/plans/2026-08-23-git-safety-guard-checklist-fix.md`
**Effective tier:** Medium (live security-guard hook edit)
**Audit rounds:** 1 (plus the pre-execution 2-round Codex plan review) · **Exit reason:** low-only round (all live findings closed; one P2 dormant-path finding deferred to TRK-179 with user approval)

## What shipped
Two independent false-NEGATIVE fixes in `hooks/git-safety-guard.py`'s pre-completion checklist, without weakening the guard:
1. `make check`/`test`/`lint` now satisfy `has_tests`/`has_lint` (substring tokens, unanchored), and commit/push are excluded from being recorded as verifications at both recording gates (closes the commit-message self-satisfy vector for all tokens).
2. The `[-20:]` count cap replaced by `_prune_verifications()` — recency-window prune (`RECENCY_WINDOW_SECONDS=1800`) then a `MAX_VERIFICATIONS=500` backstop — so an in-window verification is never evicted under realistic churn.

## Verification
- Full suite: **1550 passed, 18 skipped** (`test_git_safety_guard.py` 194 → 202, +8 tests across two commits). 1 pre-existing failure (`test_design_face_output_is_byte_identical_to_committed_digest`) caused by an untracked codex-learnings file — not in scope, passes on clean CI.
- `ruff check hooks` clean. CI `test (3.11)` + `test (3.12)` both green.

## Reviews (agents dispatched)
- Implementer ×2 (defect fixes; +4 coverage tests), Spec reviewer, Simplify auditor, Harden auditor, QA reviewer, Codex diff review.
- **Spec:** PASS. **Simplify:** P3-only. **Harden:** zero findings — guard integrity intact, no new false-ALLOW. **QA:** PASS_WITH_CONCERNS → 3 P2 test-gaps closed with 4 added tests. **Codex:** 1 P2 (below).

## Recurring pattern (signal)
- **Sibling-classifier taxonomy drift** appeared in ALL five reviews (Simplify P3, Spec off-axis note, QA finding 1, Codex P2): the `make` tokens were added to the presence regexes (`has_tests`/`has_lint`) but not the failure regexes (`failed_tests`/`failed_lint`). No live effect — the failure path is dormant in this harness (`exit_code` always None) — but a latent asymmetry when the verification-stamp phase revives that path. The recurrence across independent reviewers indicates the four sibling regexes should be built from a shared token constant (GP#11 consolidate-before-adding).

## Unresolved (deferred)
- **TRK-179** — add `make` tokens to `failed_tests`/`failed_lint` (with the correct exit-code handling; pytest's exit-code-5 exception does not apply to `make`) when the exit-code/verification-stamp path revives. Deferred with user approval; scoped out of this fix by the plan.

## Out-of-scope observations
- `_extract_exit_code` (`git-safety-guard.py:~1115`) has two no-op branches (dormant exit-code path) — flagged by Simplify, not touched.
- The `echo "make check"` literal-mention residual: a deliberate non-commit mention can still be recorded, same footing as the pre-existing `pytest`/`ruff` substring tokens. Full command-grammar hardening is a separate tracked follow-up.

## ~/.claude-side steps still pending (must run from a ~/.claude-rooted session, not here)
- **Submodule pointer bump:** `~/.claude` gitlink still points at the pre-merge coding-team commit; bump it to `b662415` via branch+PR (direct-to-main is hook-blocked). The live symlinks already reflect the fix; this is the parent-repo record.
- **Harness metrics:** append this session's Phase-6 metrics line to `~/.claude/harness-metrics.jsonl` (deferred to honor the session-root scope boundary).
