# Handoff — build + ship TRK-176 (git-safety-guard checklist false-negative fix)

## Task
Fix two false-NEGATIVE defects in the live hook `hooks/git-safety-guard.py` pre-completion verification checklist, which false-blocks legit commits with "PRE-COMPLETION CHECKLIST FAILED / have NOT run tests" even when tests passed. **The plan is DONE and fully reviewed; only the BUILD + ship remain.** This is a `/coding-team` Medium task, currently between Phase 4 (planning, complete) and Phase 5 (execution, not started).

## THE DESIGN IS FINAL — do NOT re-plan or re-review the plan
The plan went through the full Phase 4 gate this session: plan-doc reviewer **APPROVED**, then **two Codex plan-review rounds**. Round 1 caught a real guard-WEAKENING; round 2 proved the round-1 "anchored regex" fix was worse (false-negatives on `CI=1 make check`). Per interaction rule 3 (churn = stop) the design was reduced to the SIMPLE, proven version below. **Do NOT run another plan Codex round.** The remaining cross-model check is the post-exec Codex review on the actual DIFF (a Phase 5 exit gate).

**Plan file:** `docs/plans/2026-08-23-git-safety-guard-checklist-fix.md` (gitignored; `status: planned`, `instruction_files: hooks/git-safety-guard.py, hooks/tests/test_git_safety_guard.py`). It is authoritative and self-consistent — build exactly what it says.

**Final design (two changes to `hooks/git-safety-guard.py`, applied as ONE atomic edit):**
1. **Substring make-recognition** — add `|make\s+(?:check|test)` to the `has_tests` regex (~`:1302`) and `|make\s+(?:check|lint)` to `has_lint` (~`:1306`), inline in the existing `re.search(...)` alternation, exactly like the existing `pytest`/`ruff` tokens. `make check` satisfies BOTH. Do NOT anchor (anchoring was tried and rejected — it false-blocks `CI=1 make check`).
2. **Exclude commit/push from verification recording** — at BOTH recording gates add `and not is_commit_or_push(command)` (helper at `:381-382`): gate `_handle_post_tool_use` (~`:1116`) → `if not command or not is_verification(command) or is_commit_or_push(command): return`; PreToolUse fallback (~`:1186`) → `if is_verification(command) and not is_commit_or_push(command):`. Closes the realistic "a commit message mentioning a verification token self-satisfies its own checklist" vector.
Plus **Task 2** (independent): replace the `[-20:]` count cap at both write sites (`:1142`, `:1204`) with a `_prune_verifications()` helper that keeps entries within a shared `RECENCY_WINDOW_SECONDS` (30 min) then a high `MAX_VERIFICATIONS=500` backstop; checklist read (`:1299`) uses the constant. Codex confirmed Task 2 closed.
**4 new tests** (a: make check → allowed; b: churn survival; c: zero-verif blocks; d: commit-message "make check" still blocks). Real hook subprocess + real state, no mocks.

## Acceptance criteria
- Both defects fixed per the plan; full suite green from repo root (baseline **1543 passed / 18 skipped** → expect **1547 passed / 18 skipped**, +4); `python3 -m ruff check hooks` clean.
- Green PR on `cmillstead/coding-team` (checks `test (3.11)` + `test (3.12)`).
- **Merged to main** (the user wants the false-block to actually STOP — a green PR alone doesn't fix their live sessions). Because deployed hooks are symlinks to source, coding-team `main` checked out = the live fix for ALL sessions.
- Plan flipped `status: complete` at Phase 6.

## Repo state (measured 2026-08-23)
- **coding-team** (`~/.claude/skills/coding-team`, submodule of `~/.claude`): on `main`, tip `cbdbfa1` (the ci-watch merge). Working tree clean except 3 untracked files (2 handoffs + 1 codex-learnings entry) — none related to this task; leave them.
- **No plan is `in-progress`** → write-guard is dormant right now. Clean state for compaction.
- No PR for TRK-176 yet (not built).

## Remaining actions (cold-start — do in order)

### 1. Enter Phase 5 execution (read `phases/execution.md` first)
- **How:** (a) Confirm on a non-main branch — you're on `main`, so `git -C /Users/cevin/.claude/skills/coding-team checkout -b fix/trk-176-checklist-false-negatives origin/main`. (b) Flip the plan: Edit `docs/plans/2026-08-23-git-safety-guard-checklist-fix.md` frontmatter `status: planned` → `status: in-progress` (orchestrator's own edit; arms write-guard for the 2 declared instruction_files). (c) Baseline: run the full suite `python3 -m pytest -q` from the repo root — expect 1543 passed / 18 skipped; if not green, fix before dispatching (do not label failures "pre-existing").
- **Looks-broken-but-isnt:** the plan file is gitignored — that's expected; it is NOT committed and the fix commits are only the hook + test file. `docs/plans/` being absent from `git status` is correct.
- **Canonical home:** `phases/execution.md` (the Phase 5 protocol).

### 2. Dispatch ONE implementer (Task 1 + Task 2, TDD) via the Agent tool
- **How:** COORDINATION=no, single implementer owns both files. Pass the FULL text of Task 1 and Task 2 from the plan (do not make the implementer read the plan). Include the plan's **live-hook wedge-hazard** warning verbatim: after each edit to `git-safety-guard.py`, probe `echo '{}' | python3 hooks/git-safety-guard.py` (clean exit, no traceback) BEFORE any git/Bash call — a broken edit fails-closed and blocks Bash. Apply the two Task-1 changes as ONE atomic save (never leave the live hook in "make recognized, commit not excluded" state).
- **Looks-broken-but-isnt / GOTCHA (this is the very bug being fixed, still live until merged):** the implementer's OWN `git commit` calls will hit the pre-completion checklist. Until the fix is in the working tree, the OLD buggy guard is live; even after, a concurrent test flood can evict records. Mitigation (already in the plan): run `python3 -m ruff check hooks` and/or `python3 -m pytest -q` from the repo root **immediately before each commit** so a fresh pass is in the window; if still blocked, run `ruff check` as the LAST command before the commit. Do NOT bypass with `WRITE_GUARD_ALLOW_*` or `--no-verify` (hook-bypass rule; and see [[feedback_verification-buffer-eviction-blocks-pushes]] / TRK-176 is literally this).
- **Canonical home:** `~/.claude/agents/ct-implementer.md`; plan Tasks 1-2.

### 3. Per-task completeness check + audit loop
- **How:** after the implementer reports, count items done vs spec (2 code changes + 4 tests); re-dispatch if short. Run the audit loop (`phases/audit-loop.md`): spec + simplify + harden auditors on the diff. Fix all P0-P2 findings; stop-line per the plan's `## Review-loop stop-line` (ship on ≤P3 or churn).
- **Canonical home:** `phases/audit-loop.md`.

### 4. Exit gates (all required at Medium — read `phases/execution.md` "Effective-Tier Recompute" onward)
- **How, in order:** (a) effective-tier recompute (stays Medium — it's a hook edit). (b) full-suite `python3 -m pytest -q` from repo root + `python3 -m ruff check hooks`, both clean; name the collected total (expect 1547 passed / 18 skipped). (c) `ct-qa-reviewer` via Agent tool on the full diff. (d) doc-drift scan (`phases/doc-drift-scan.md`). (e) **post-exec Codex review on the DIFF** (`phases/post-execution-review.md`) — this is the final cross-model check; `codex review --base main` (codex is at `/Users/cevin/.nvm/versions/node/v20.19.6/bin/codex`; run from repo root; `< /dev/null`; judge from output content not pipe exit).
- **Looks-broken-but-isnt:** a subdir pytest run is NOT the suite — always run `python3 -m pytest -q` from the repo ROOT and name the scope ([[feedback_subdir-test-run-is-not-full-suite]]).
- **Canonical home:** `phases/task-weight.md` gate matrix (Medium row); `phases/post-execution-review.md`.

### 5. Phase 6 completion (read `phases/completion.md`)
- **How:** create the PR (`/release` skill, NOT gstack `/ship`); watch `gh pr checks <n> --repo cmillstead/coding-team` until `test (3.11)` + `test (3.12)` pass. **Merge** (user wants it live). Then sync local main (`git checkout main && git pull --ff-only origin main`), delete the feature branch, and flip the plan `status: in-progress` → `status: complete`. File a follow-up TRK for the documented command-grammar-hardening residual (the plan's NOT-in-scope bullet: pytest/ruff/make detection is substring, so a deliberate `echo "make check"` mention can still satisfy — pre-existing, tracked separately).
- **Looks-broken-but-isnt:** the plan has no `- [ ] Second-opinion review` checkbox (custom format, like the ci-watch plan). Flipping to `complete` did NOT block for ci-watch; if the lifecycle hook does block, add the checkbox line as `- [x]` (the second-opinion review genuinely ran — 2 rounds). This is the orchestrator's own frontmatter/checkbox edit.
- **Canonical home:** `phases/completion.md`; [[feedback_coding-team-two-repo-ship-flow]] (the `~/.claude` submodule-pointer bump is a separate `~/.claude`-side step — the live symlink already reflects coding-team main once merged+checked-out, so the pointer bump is for the parent-repo record, done from a `~/.claude` session).

## Blockers / paused
- None. All work is coding-team-scoped (editing coding-team's own hook + tests) — in-scope for this session's root.

## Other open threads (do NOT lose — not part of this build)
- **ci-watch activation (TRK-031):** merged to coding-team main this session; NOT yet turned on. Full steps in `docs/handoff/2026-08-23-ci-watch-merge-activate.md` — the user is doing this from a separate `~/.claude`-rooted session.
- **TRK-178:** give the migration-edit guard a scoped, plan-declared, self-clearing permission and delete `WRITE_GUARD_ALLOW_MIGRATION_EDIT` — the user's standing rule: NEVER a session env var they must manually revert ([[feedback-escape-hatch-granularity]], updated this session).
- **Command-grammar hardening** (the TRK-176 residual above) — to be filed at Phase 6.

## Completed this session (context — do not redo)
- ci-watch PR #155 merged to coding-team main; `/save` done (ci-watch shipped log + 2 feedback memories); TRK-176 and TRK-178 logged; TRK-176 plan written, reviewed (plan-doc APPROVED + 2 Codex rounds), and reduced to the final simple design.

## Related
- Plan: `docs/plans/2026-08-23-git-safety-guard-checklist-fix.md`
- `phases/execution.md`, `phases/completion.md`, `phases/task-weight.md`
- tracker: TRK-176 (this), TRK-178, TRK-031
