# Handoff — merge PR #155 + activate ci-watch, then /save

## Task
The user chose **option 1**: merge the green ci-watch PR (#155), **activate** it in the live `~/.claude` setup (deploy the 3 hooks + bump the submodule pointer), then `/save` the session. The build is DONE and CI-green; only the ship + activate + save remain. User said "compact first, then 1" — this handoff is what a fresh post-compact session executes.

## Acceptance criteria
- PR #155 merged into `cmillstead/coding-team` main (merge-commit, matching #154's style).
- Local coding-team synced to main (`feat/ci-watch` deleted local+remote).
- ci-watch **activated**: the 3 hooks symlinked into `~/.claude/hooks/`, and the `~/.claude` submodule pointer bumped to the new coding-team main SHA (via a `~/.claude` branch + PR — direct-to-main is hook-blocked).
- The ci-watch plan flipped `status: in-progress` → `status: complete` and its Completion Checklist `Second-opinion review` box checked.
- `/save` run (content captured below so it survives compaction).

## Repo state (measured 2026-08-23)
- **coding-team** (`~/.claude/skills/coding-team`, a submodule of `~/.claude`): on branch `feat/ci-watch`, tip `194a189`. PR **#155** OPEN, MERGEABLE, mergeStateStatus CLEAN, base `main`. **CI GREEN** (test 3.11 + test 3.12 both passed, 0 failed). Local full suite: 1543 passed / 0 failed / 18 skipped; ruff clean.
- **Plan** (armed): `docs/plans/2026-08-22-ci-watch.md`, `status: in-progress`, `instruction_files:` declares the 6 hook/test files. write-guard is armed for those 6 files until the status flips to complete.
- **~/.claude** (parent repo): on `main`; submodule pointer recorded at `17eb69d` (the prior process-rules SHA); `git status` shows ` M skills/coding-team` because the submodule working tree is on `feat/ci-watch` (ahead of the recorded pointer) — expected, resolved by the pointer bump.
- **Deploy model:** deployed hooks are **relative symlinks** into the submodule (`~/.claude/hooks/git-safety-guard.py -> ../skills/coding-team/hooks/git-safety-guard.py`). `scripts/deploy.sh` (755) creates/refreshes them. The 3 ci-watch hooks are currently **absent** from `~/.claude/hooks/` → feature dormant (the dispatchers reference them but the existence-guard skips a missing handler).

## Remaining actions (cold-start — do in order)

### 1. Verify #155 is still green + mergeable
- **How:** `gh pr checks 155 --repo cmillstead/coding-team` (expect Passed: 2, Failed: 0) and `gh pr view 155 --repo cmillstead/coding-team --json state,mergeable,mergeStateStatus` (expect OPEN/MERGEABLE/CLEAN).
- **Looks-broken-but-isnt:** if `gh pr checks` prints nothing, checks may have aged out of the API view — trust the recorded green above only if the head SHA is unchanged (`194a189`).

### 2. Merge #155
- **How:** `gh pr merge 155 --repo cmillstead/coding-team --merge` (merge-commit, like #154). Then note the new main SHA: `gh api repos/cmillstead/coding-team/commits/main --jq .sha`.
- **Looks-broken-but-isnt:** `gh pr merge` merges on GitHub only — it does NOT move the local checkout (that's step 3).

### 3. Sync local coding-team to main + delete the feature branch
- **How:** `git -C /Users/cevin/.claude/skills/coding-team checkout main` → `git -C /Users/cevin/.claude/skills/coding-team pull --ff-only` → confirm main now contains the ci-watch hooks (`ls /Users/cevin/.claude/skills/coding-team/hooks/ci-watch-arm.py`). Then `git -C /Users/cevin/.claude/skills/coding-team branch -d feat/ci-watch` and `git -C /Users/cevin/.claude/skills/coding-team push origin --delete feat/ci-watch`.
- **Looks-broken-but-isnt:** `branch -d` may refuse ("not fully merged") because the merge was a merge-commit on the remote; safe to `-D` here — the work is on main (verify with `git -C … log main --oneline | grep -i ci-watch`).

### 4. Flip the plan to complete (do this from THIS coding-team session, before deploy)
- **How:** Edit `docs/plans/2026-08-22-ci-watch.md`: `status: in-progress` → `status: complete`, AND change `- [ ] Second-opinion review` to `- [x] Second-opinion review` (the lifecycle hook reads that box). This is the orchestrator's own frontmatter edit — allowed. Flipping to complete disarms write-guard for the 6 files.
- **Canonical home:** the plan file itself is the durable state the lifecycle hook reads.

### 5. Activate — deploy the hooks (a `~/.claude`-side step; user authorized via option 1)
- **How:** run the deploy script so it symlinks the 3 ci-watch hooks into `~/.claude/hooks/`: `bash /Users/cevin/.claude/skills/coding-team/scripts/deploy.sh` (must run with coding-team on **main**, step 3 done first). Then verify: `ls -la /Users/cevin/.claude/hooks/ci-watch-arm.py /Users/cevin/.claude/hooks/ci-watcher.py /Users/cevin/.claude/hooks/ci-watch-inject.py` — all three should now be symlinks into `../skills/coding-team/hooks/`.
- **Looks-broken-but-isnt:** deploy.sh intentionally treats `ci-watcher.py` as a **spawned helper** (exempt from the "deployed but not registered" verifier) — it is still symlinked/on disk so `arm` can spawn it; the exemption only silences the registration warning. Absence of a registration line for ci-watcher.py is correct, not a bug.
- **Session-root note:** deploying into `~/.claude/hooks/` and the pointer bump below are `~/.claude`-side operations. The user chose activation (option 1) and has authorized this cross-repo pattern before (process-rules ship, [[feedback_coding-team-two-repo-ship-flow]]). deploy.sh from the **main** checkout (not a worktree) is the normal, safe deploy.

### 6. Activate — bump the ~/.claude submodule pointer (branch + PR; direct-to-main is hook-blocked)
- **How:** `git -C /Users/cevin/.claude checkout -b chore/bump-coding-team-ci-watch` → `git -C /Users/cevin/.claude add skills/coding-team` → `git -C /Users/cevin/.claude commit -m "chore: bump coding-team pointer — ci-watch (PR #155)"` → `git -C /Users/cevin/.claude push -u origin chore/bump-coding-team-ci-watch` → `gh pr create --repo <the ~/.claude remote> --base main --head chore/bump-coding-team-ci-watch --title "chore: bump coding-team pointer — ci-watch" --body "Activates ci-watch (coding-team PR #155)."` → merge that PR → sync `~/.claude` main.
- **Looks-broken-but-isnt / GOTCHA (verification-buffer):** the `git commit`/`git push` in this step can be **blocked by the pre-completion checklist** even though everything is verified. Root cause (diagnosed this session): git-safety-guard's own test suite writes to the real session file `/tmp/claude-verification-<sha256(session_id)[:12]>.json`, and the `[-20:]` cap means a full `pytest` run floods the buffer with test-fixture git commands and **evicts** your genuine lint/test records; also successful commands record `exit_code: null` in this env. **Fix:** run `python3 -m ruff check /Users/cevin/.claude/skills/coding-team/hooks` (or the relevant path) as the **last command immediately before** the blocked commit/push — nothing after it to evict it — then retry. Confirm it's the last entry in that /tmp file if still stuck. Do NOT bypass with `--no-verify` or env overrides (hook-bypass rule). This is a pre-existing bug worth its own fix later (see /save content).
- **Canonical home:** [[feedback_coding-team-two-repo-ship-flow]] (the two-repo ship pattern).

### 7. Confirm activation is live + clean
- **How:** the 3 symlinks exist (step 5), `~/.claude` submodule pointer now equals the new coding-team main SHA (`git -C /Users/cevin/.claude ls-tree HEAD skills/coding-team`), and `git -C /Users/cevin/.claude status --short skills/coding-team` is clean. ci-watch is now armed on real pushes — expect it to fire on YOUR next push/merge (it watches its own activity now; that's the feature working, not a bug).

### 8. /save the session
Run `/save`. If compaction dropped the detail, save at minimum these (content below):

## /save content (capture even if the conversation was compacted)
1. **Project/vault log — ci-watch v1 shipped.** coding-team PR #155 (bounded post-push CI watcher, TRK-031). Design headline: **key off GitHub's run-level conclusion, do NOT parse workflow YAML** (GitHub already folds job-level continue-on-error into the run conclusion) — this eliminated a whole class of silent-suppression bugs by construction. Honest-scoping call after 3 Codex rounds kept finding never-miss edge cases: v1 is a **bounded ~20-min best-effort watcher** that never suppresses/mislabels a run it OBSERVES and never false-greens; late/re-run/chained/merge-queue/`--auto` are documented fail-safe limitations, not bugs. Build: 13-task TDD + 2 fix rounds; passed spec/simplify/QA/harden + 2 Codex plan rounds + 1 Codex post-exec round; 1543 tests pass.
2. **feedback memory — security audit catches what plan review misses.** The 3 Codex plan rounds all focused on the never-miss *logic*; the **harden audit** found the real trust-boundary bugs the plan reviews missed: a world-writable `/tmp` fallback dir (FIFO/symlink/oversized DoS + poisoned-marker), and **unsanitized CI job names injected into Claude's prompt context** (prompt injection). Lesson: for a feature that writes into the prompt stream or shares filesystem state, run a dedicated trust-boundary/harden pass — logic review ≠ security review. Fixed with uid-scoped 0700 state, `O_NOFOLLOW|O_NONBLOCK`+fstat reads, sanitize+fence, per-marker isolation.
3. **feedback memory — verification-buffer eviction blocks legitimate pushes.** `git-safety-guard.py`'s pre-completion checklist stores passed lint/test in `/tmp/claude-verification-<hash>.json` capped at `[-20:]`; its OWN test suite writes to that real session file, so running the full `pytest` suite evicts your genuine records and the push is blocked. Successful commands also record `exit_code: null` in this env. Workaround: run `ruff check` as the LAST command before the push. Real fix (later): isolate the state file in the tests (override session id / path) and/or treat `exit_code: null` from a matched verification as pass. Link [[feedback_coding-team-two-repo-ship-flow]].

## Decisions made this session (with canonical homes)
- **Activate ci-watch (option 1)** → this handoff + (after merge) the plan marked complete.
- **Bounded honest-scope over never-miss-completeness** → the plan's contract section + the vault log above. Rationale: a 20-min local watcher cannot guarantee catching late/re-run/chained runs; chasing it by construction did not converge across 3 Codex rounds.
- **compound-allow port still parked** → **TRK-171** (unrelated to ci-watch; do not lose it).
- **Branch review closed** → **TRK-170** done earlier this session.

## Blockers / paused
- None technical. Activation is paused only for the user's /compact. The verification-buffer quirk (step 6) is a known, worked-around friction, not a blocker.

## Completed this session (context — do not redo)
- Reviewed 21 unmerged branches → 19 deleted (already on main), 1 parked (TRK-171), 1 (wip/ci-watch) became this build.
- Built ci-watch to a green PR #155 (full pipeline: plan → 3 Codex plan rounds/re-scope → build → audit+QA+harden → 2 fix rounds → post-exec Codex → green CI).

## Related
- `feedback_coding-team-two-repo-ship-flow` (memory) — the merge + pointer-bump pattern
- `feedback_session-root-is-the-scope-boundary` (memory)
- Plan: `docs/plans/2026-08-22-ci-watch.md`
- PR: https://github.com/cmillstead/coding-team/pull/155
- tracker: TRK-031 (ci-watch), TRK-171 (parked compound-allow port)
