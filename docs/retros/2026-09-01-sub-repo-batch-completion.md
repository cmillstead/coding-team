# Completion Summary — sub-repo batch (TRK-193b / 196 / 197)

**Shipped:** 2026-09-01. Submodule PR #158 (merge c8a47d0) + parent pointer bump PR #144 (merge 31ffa69). CI green (test 3.11 + 3.12). Full suite 1500 passed.

**Tier:** Medium. **Audit rounds:** 1 (per-task on the hook code). **Exit reason:** low-only.

## What shipped (5 findings, one PR)
1. `agents/ct-implementer.md` — test-files/no-mocks pointer (Gap 2b).
2. `hooks/deploy-drift-check.py` + tests — advisory stdlib-name-collision check; `main()` restructured so drift + collision advisories fire independently; 8 TDD tests incl. a mutation-verified independence pin (Gap 6).
3. `phases/execution.md` — wired orphaned `precomputation.md` via `@`-ref (Gap 7, user chose WIRE).
4. `phases/spec-review.md` — seam-ownership checklist step (TRK-197).
5. `skills/doc-sync/SKILL.md` — flag-only CLAUDE.md staleness scan (TRK-196).

## Recurring pattern (the signal)
**Existing-state hazards caught by review, missed by the planner** — appeared twice, both HIGH, both in the hook task:
- Plan-doc reviewer: the test file already existed → a "Create" would have wiped 5 tests. Fixed to append.
- Codex plan review: the hook's `if not drifted: return` early return made the new collision scan unreachable on the no-drift path — the exact path the test needed. Fixed by restructuring `main()`.
- Lesson: a planner working from a spec doesn't re-verify current file/function state; the cross-model + plan-doc reviews are what catch "the code already does X / the file already exists." Both were load-bearing.

## Also fixed in-flight
- Harness-engineer (LOW): warning advised a `base-` prefix — reintroduces the term the harness just retired (PR #143). Changed to descriptive-hyphenated naming.
- QA (MEDIUM): the `main()` independence property was untested (both existing tests zeroed out drift). Added a drift+collision-present test; mutation-verified it goes RED under re-coupling.

## Deferred
- TRK-205 (p3, MAIN repo): strip stale `globs:`/`~/.claude/rules/` cruft from `precomputation.md` now that it loads via `@`-ref. Cosmetic; separate repo.

## Gates
Plan-doc review; Codex plan review (2 rounds); per-task audit (spec/TDD, simplify, harden, harness-engineer); feature QA; prompt-craft audit; Codex post-exec diff review (APPROVED). All passed.
