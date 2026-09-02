# Handoff — ~/.claude-side activation: deploy ci-watch, bump the pointer (covers ci-watch + TRK-176), append metrics

## Run this from a `~/.claude`-rooted session
This session must start in `~/.claude` (NOT `~/.claude/skills/coding-team`). A coding-team session must not touch the parent repo — that is why this work was deferred here. See [[feedback_session-root-is-the-scope-boundary]] and [[feedback_coding-team-two-repo-ship-flow]].

## Task
Two coding-team ships are merged to coding-team `main` but not yet reflected in the live `~/.claude` deployment:
1. **ci-watch v1** (PR #155, TRK-031) — merged, but its 3 hooks are NOT deployed (feature dormant).
2. **TRK-176 git-safety-guard checklist fix** (PR #156) — merged; the fix is ALREADY live for coding-team sessions (deployed hooks are symlinks into the submodule source), but the parent-repo submodule POINTER still records an older SHA.

One pointer bump to coding-team main `b662415` rolls up BOTH ships (b662415 sits on top of the ci-watch merge). Then deploy the ci-watch hooks and append the TRK-176 metrics line.

## Acceptance criteria
- The 3 ci-watch hooks (`ci-watch-arm.py`, `ci-watcher.py`, `ci-watch-inject.py`) are symlinked into `~/.claude/hooks/`.
- The `~/.claude` submodule pointer for `skills/coding-team` equals `b662415`; `git -C ~/.claude status --short skills/coding-team` is clean.
- One `harness-metrics.jsonl` line appended for TRK-176.

## Repo state (measured 2026-08-24 from the coding-team session that merged both)
- **coding-team** (`~/.claude/skills/coding-team`): on `main`, tip **`b662415`** (merge of TRK-176 PR #156, which sits on top of ci-watch merge `cbdbfa1`). Working tree clean except 4 pre-existing untracked files (3 handoffs incl. this one + 1 codex-learnings entry) — leave them. Both plans (`2026-08-22-ci-watch.md`, `2026-08-23-git-safety-guard-checklist-fix.md`) are `status: complete`.
- **~/.claude** (parent repo): last-known recorded submodule pointer was `17eb69d` (process-rules SHA, per the 2026-08-23 ci-watch handoff); neither ci-watch nor TRK-176 has bumped it, so `git -C ~/.claude status` shows ` M skills/coding-team`. **Verify the actual current pointer** at session start: `git -C /Users/cevin/.claude ls-tree HEAD skills/coding-team` — whatever it is, the target is `b662415`.
- **Deploy model:** deployed hooks are RELATIVE symlinks into the submodule (`~/.claude/hooks/git-safety-guard.py -> ../skills/coding-team/hooks/git-safety-guard.py`). `scripts/deploy.sh` (755) creates/refreshes them. The 3 ci-watch hooks are currently ABSENT from `~/.claude/hooks/` → ci-watch dormant.

## Remaining actions (cold-start — do in order)

### 1. Deploy the ci-watch hooks
- **How:** with coding-team on `main` (it is — `b662415`), run `bash /Users/cevin/.claude/skills/coding-team/scripts/deploy.sh`. Then verify all three are symlinks: `ls -la /Users/cevin/.claude/hooks/ci-watch-arm.py /Users/cevin/.claude/hooks/ci-watcher.py /Users/cevin/.claude/hooks/ci-watch-inject.py` — each should point into `../skills/coding-team/hooks/`.
- **Looks-broken-but-isnt:** deploy.sh treats `ci-watcher.py` as a SPAWNED helper — it is symlinked/on disk (so `arm` can spawn it) but is intentionally exempt from the "deployed but not registered" verifier. No registration line for `ci-watcher.py` is correct, not a bug.
- **Canonical home:** the full ci-watch activation detail is in `docs/handoff/2026-08-23-ci-watch-merge-activate.md` steps 5 and 7 (steps 1–4 there are ALREADY DONE — do not redo the merge/sync/plan-flip).

### 2. Bump the ~/.claude submodule pointer to `b662415` (branch + PR — direct-to-main is hook-blocked)
- **How:**
  - `git -C /Users/cevin/.claude checkout -b chore/bump-coding-team-trk176-ciwatch`
  - `git -C /Users/cevin/.claude add skills/coding-team` (records the submodule at its checked-out `b662415`)
  - `git -C /Users/cevin/.claude commit -m "chore: bump coding-team pointer — ci-watch (#155) + TRK-176 (#156)"`
  - `git -C /Users/cevin/.claude push -u origin chore/bump-coding-team-trk176-ciwatch`
  - `gh pr create --base main --head chore/bump-coding-team-trk176-ciwatch --title "chore: bump coding-team pointer — ci-watch + TRK-176" --body "Rolls up ci-watch (coding-team PR #155) and the TRK-176 checklist fix (PR #156) to coding-team main b662415."` (run from `/Users/cevin/.claude`; add `--repo <owner/claude-harness-repo>` if gh doesn't infer it)
  - merge that PR, then sync: `git -C /Users/cevin/.claude checkout main && git -C /Users/cevin/.claude pull --ff-only`
- **Looks-broken-but-isnt / GOTCHA (now mostly fixed):** the `git commit`/`git push` here hits the pre-completion checklist. The verification-buffer EVICTION bug that used to block this is exactly what TRK-176 fixed — once step 1 deploys and coding-team is on `b662415`, the live guard prunes by recency window, so churn no longer evicts a real pass. BUT the checklist still wants SOME recent test/lint pass in the 30-min window, and a pointer-bump commit runs no tests. So run `python3 -m ruff check /Users/cevin/.claude/skills/coding-team/hooks` as the LAST command immediately before the commit. Do NOT bypass with `--no-verify` or any `WRITE_GUARD_ALLOW_*` env var (hook-bypass rule).
- **Canonical home:** [[feedback_coding-team-two-repo-ship-flow]] (the two-repo ship pattern); [[feedback_verification-buffer-eviction-blocks-pushes]] (the friction, now fixed by TRK-176).

### 3. Append the TRK-176 harness-metrics line
- **How:** append this one line to `~/.claude/harness-metrics.jsonl` (via an editor/Write, not a shell heredoc — JSON in a shell command trips the permission heuristic):
```json
{"date":"2026-08-24","project":"coding-team","task":"trk-176-git-safety-guard-checklist-fix","phases_used":["plan","execute","audit","complete"],"agents_dispatched":{"builder":2,"reviewer":1,"qa":1,"harden":1,"simplify":1,"prompt":0},"audit_rounds":1,"audit_exit":"low-only","findings_total":4,"findings_fixed":3,"findings_deferred":1,"rework_iterations":1,"test_pass_first_try":true,"ci_pass_first_push":true,"second_opinion":"ran","second_opinion_outcome":"completed-no-changes","elapsed_phases":{"design":null,"plan":null,"execute":null,"audit":null}}
```
- **Looks-broken-but-isnt:** `phases_used` MUST stay a JSON array and `elapsed_phases` a JSON object, or the TRK-016 validator flags it and it under-reports phase heat. `second_opinion_outcome` is `completed-no-changes` because the one Codex P2 was DEFERRED (TRK-179), not fixed into this diff.
- **Canonical home:** `phases/completion.md` "Harness Metrics Capture" (template + the validation guard to run after appending).

### 4. Confirm live + clean
- **How:** `git -C /Users/cevin/.claude ls-tree HEAD skills/coding-team` equals `b662415`; `git -C /Users/cevin/.claude status --short skills/coding-team` is empty; the 3 ci-watch symlinks exist (step 1).
- **Looks-broken-but-isnt:** ci-watch now arms on real pushes — expect it to fire on the NEXT push/merge in this same session (it watches your own activity now; that's the feature working).

## Blockers / paused
- None. All authorized: the user chose activation and the pointer bump explicitly this session.

## What is ALREADY done (do NOT redo)
- ci-watch PR #155 merged (`cbdbfa1`), TRK-176 PR #156 merged (`b662415`); both feature branches deleted local+remote; both plans flipped `status: complete`; both sessions `/save`-d. The ONLY unshipped piece is the ~/.claude-side activation above.

## Open follow-ups (tracker — not part of this activation)
- **TRK-179** — mirror `make` tokens into the dormant `failed_tests`/`failed_lint` regexes (or consolidate the token set into one shared constant) when the exit-code/verification-stamp path revives.
- **TRK-178** — give the migration-edit guard a scoped, plan-declared, self-clearing permission; delete `WRITE_GUARD_ALLOW_MIGRATION_EDIT`.
- **TRK-171** — parked compound-allow port (from the ci-watch session).

## Related
- `docs/handoff/2026-08-23-ci-watch-merge-activate.md` — the original ci-watch activation detail (steps 5/7 still apply; 1–4 done)
- `docs/retros/2026-08-24-trk-176-git-safety-guard-checklist-fix.md` and `...-completion.md` — TRK-176 detail
- Plans: `docs/plans/2026-08-22-ci-watch.md`, `docs/plans/2026-08-23-git-safety-guard-checklist-fix.md`
