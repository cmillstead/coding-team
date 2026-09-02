# Retrospective: TRK-176 git-safety-guard checklist false-negative fix

**Shipped 2026-08-24 · PR #156 → main `b662415`**

### What went well
- **TDD discipline held on a live security guard.** Both behavior-changing tests (a: make-check allowed; b: in-window pass survives churn) were shown RED before the fix and GREEN after — real hook subprocess + real state, no mocks. The two scope-regression guards (c, d) were correctly exempted from RED-first and stayed green both sides.
- **Cross-model review earned its slot by convergence, not novelty.** Codex's single P2 was the exact dormant-path asymmetry the internal Simplify/Spec/QA reviewers also raised — five independent lenses landing on one finding is high-confidence signal, and it's what justified pre-filing the follow-up rather than hand-waving it.
- **Harden pass returned zero findings on the guard itself** — no new false-ALLOW, every existing block path byte-for-byte intact. For a change to a security hook, that's the load-bearing result.
- **No rework commits.** 3 clean commits, no fixups, no fix-of-fix. The plan was precise enough (exact line numbers, verbatim code, atomic-edit note) that the implementer built it in one pass.
- **The corridor held on the P2.** The dormant-path finding was off-axis (it's the failure-advisory path, not the false-block path that was hurting the user); it was deferred-with-approval to TRK-179 instead of triggering a rabbit-hole into dormant exit-code logic.

### What to improve
- **The sibling-classifier asymmetry should have been decided at plan time, not surfaced by every reviewer.** The plan's "NOT in scope" reasoning was sound (dormant path, exit-code nuance), but because the follow-up (TRK-179) wasn't filed until Phase 6, five reviewers each spent effort re-flagging it. Pre-filing the residual as part of the plan's scope decision would have converted five findings into zero.
- **A dirty working tree from a prior session cost a verification detour.** The baseline full-suite run showed 1 failing test (`test_design_face_output_is_byte_identical_to_committed_digest`) caused by an untracked codex-learnings file left over from an earlier session. It was correctly diagnosed as not-mine and CI-invisible, but it forced a root-cause pass before the build could start. A clean tree at session start would have removed the ambiguity.

### Recurring patterns
- **Sibling-classifier taxonomy drift** — a token added to one classifier (`has_tests`/`has_lint`) not mirrored to its opposite-polarity sibling (`failed_tests`/`failed_lint`). Captured as a reusable lesson: `feedback_sibling-classifier-taxonomy-drift.md`. The durable fix is consolidation (one shared token constant both siblings build from), tracked as TRK-179's framing.
- **Self-referential verification-buffer eviction** — the very bug being fixed (defect 2) also afflicted the implementer's own `git commit` calls, since the old buggy guard was live until merge. Mitigated by running ruff/pytest immediately before each commit. Already banked as `feedback_verification-buffer-eviction-blocks-pushes.md`.

### Metrics
- Commits: 3 total (2 fix, 1 test, 0 feature, 0 docs)
- Files changed: 2 (`hooks/git-safety-guard.py`, `hooks/tests/test_git_safety_guard.py`)
- Rework ratio: 0 / 3
- Test commits: every fix commit shipped its tests; +1 dedicated coverage commit (8 new tests total)
- Guard code net: ~33 lines; test code: ~227 lines (test-heavy, appropriate for a security guard)
- Reviews: 4 internal (spec/simplify/harden/QA) + 1 Codex diff review; 1 P2 (deferred TRK-179), 0 P0/P1
- Full suite: 1550 passed / 18 skipped (1 pre-existing untracked-file failure); CI green both Pythons

### Action items
- [ ] TRK-179: mirror `make` tokens into `failed_tests`/`failed_lint` (with correct exit-code handling — pytest's exit-code-5 exception does not apply to `make`), OR consolidate the shared token set into one constant all four sibling regexes build from, when the exit-code/verification-stamp path revives.
- [ ] Commit or remove the untracked `skills/second-opinion/codex-learnings.d/20260823-211710-22a7-user-args-override-daemon-args.md` so the design-face digest test stops failing locally (from a session authorized to touch second-opinion).
- [ ] ~/.claude-side (separate session): bump the submodule pointer to `b662415` and append the harness-metrics line.

### Completion Summary
The full Phase-6 completion summary lives at `docs/retros/2026-08-24-trk-176-git-safety-guard-completion.md` (audit-round detail, review verdicts, deferred items, pending ~/.claude steps).
