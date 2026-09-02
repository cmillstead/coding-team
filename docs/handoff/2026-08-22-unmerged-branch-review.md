# Handoff — review the 21 unmerged local branches (coding-team)

## Task
Review all 21 unmerged local branches in `~/.claude/skills/coding-team`, decide a per-branch disposition (MERGE / KEEP / DROP), and merge what makes sense. **User instruction, verbatim intent:** "keep them all, and lets review everything, then keep and merge what makes sense. this is exactly the kind of dropping through the cracks thing that you always do. no more." → Do NOT force-delete anything. Triage each branch, propose a disposition, merge the good ones through proper PRs.

## Acceptance criteria
- Each of the 21 branches has a written disposition with a one-line reason: **MERGE** (via PR), **KEEP** (still useful, not ready to merge), or **DROP** (superseded/obsolete).
- A per-branch disposition table is shown to the user **before** anything is deleted.
- No unmerged branch is deleted without explicit user sign-off (each holds the only copy of its work; `git reflog` keeps a deleted branch ~90 days, then it is gone).
- Branches chosen to MERGE go through the normal flow (PR → CI green → merge-commit); if the merge changes coding-team files, the `~/.claude` submodule pointer is bumped per the two-repo flow (see Decisions).
- Done signal: the SessionStart stale-branch list shrinks to only branches deliberately KEPT.

## Repo state (measured 2026-08-22)
- Repo: `~/.claude/skills/coding-team` — a **submodule** of `~/.claude`.
- Branch: `main`; working tree clean; synced with `origin/main`.
- HEAD: `17eb69d` (Merge PR #154 — process-rules gates). The `~/.claude` submodule pointer already records this (claude-harness PR #140, merged).
- Open PRs: none.
- 41 already-merged local branches were deleted this session with `git branch -d`; the 21 below remain because their commits are NOT ancestors of `main`.

## The 21 branches (last-commit date | tip subject)
```
fix/codex-exec-stdin-redirect            | 2026-08-15 | fix: gate git subcommands behind global options in git-safety-guard (TRK-136)
feat/harness-engineer-audit-fixes        | 2026-07-16 | fix: Codex-challenge remediation — prediction timing/scope, thresholds, receipts, freshness guard
wip/ci-watch                             | 2026-07-10 | wip: ci-watch hooks (arm/inject/watcher) + dispatcher wiring
harness/compound-allow-benign-redirect   | 2026-06-24 | fix: require complete-word terminator on fd-dup redirect strip
harness/compound-allow-loops             | 2026-06-24 | feat: auto-allow read-only loop compounds in compound_allow
harness/interaction-mandatory-rules      | 2026-06-24 | feat: document mandatory interaction rules + add interaction-mandatory.md
feat/codex-learning-engine-phase1        | 2026-06-20 | refactor: make digest gate grammar-free (drop git-command parsing)
codex-learnings-c13-c15                  | 2026-06-14 | docs: tighten Codex second-opinion gate guidance from c13-c15
fix/restore-handoff-guidance             | 2026-06-07 | fix: restore durable-handoff guidance clobbered from CLAUDE.md
fix/deploy-symlinks                      | 2026-06-07 | docs: README deploy description → relative-symlink approach
fix/detrack-deployed-hooks               | 2026-06-07 | fix: back-port deployed hook fixes + deploy.sh gitignore management
fix/branch-check-chaining-bypass         | 2026-06-07 | fix: script-less package.json no longer triggers un-satisfiable verification
fix/git-safety-guard-pointer-exemption   | 2026-06-07 | fix: reconcile source hooks with deployed superset + gitlink-pointer exemption
fix/second-opinion-codex-learnings-seed  | 2026-06-07 | docs(second-opinion): add C2-C3 patterns
fix/git-safety-guard-cwd                 | 2026-06-06 | wip: git-safety-guard cwd resolution + write-guard/health-check work
docs/promote-deploy-source-rule          | 2026-06-06 | docs: promote 'edit hook source not deployed' to session-loaded feedback
docs/retro-agent-hook-outage             | 2026-06-06 | docs: retrospective for Agent-tool hook outage fix (#60/#62/#61)
fix/hooks-hardening                      | 2026-06-06 | fix: harden codesight-hooks and output.py against resilience defects
fix/deploy-drift-check                   | 2026-06-06 | feat: SessionStart hook detecting source/deployed hook drift
fix/update-input-merge                   | 2026-06-06 | fix: merge-safe update_input helper preserves all tool_input fields
feat/harness-audit-fixes-2026-03-25      | 2026-03-25 | feat: register 4 new hooks in settings.json + add plan (Task 11)
```

Grouping leads (VERIFY per branch — do not trust these hunches):
- **June 6–7 cluster (12 branches)** — all tied to the Agent-tool hook-outage era; `docs/retro-agent-hook-outage` says that outage was fixed via #60/#62/#61, so several of these may already be on main under different SHAs (squash). Check each against main before treating as unique work.
- **fix/codex-exec-stdin-redirect** (Aug 15) — branch name says stdin-redirect but the tip subject is TRK-136 git-safety global-options; the two got tangled. Inspect what it actually contains. Related tracker: TRK-136 shipped separately (`2026-08-14-trk-136-git-global-options`), so this may be superseded — verify.
- **wip/ci-watch** (Jul 10) — matches tracker **TRK-031** ("coding-team: ci-watch feature is unfinished and unwired"). Disposition here should reconcile with TRK-031.
- **harness/interaction-mandatory-rules** (Jun 24) — `rules/interaction-mandatory.md` already exists live and is loaded every session, so this branch's content likely already landed; verify it adds nothing new.

## Remaining actions (cold-start)

1. **Inspect each of the 21 branches.** For each `<branch>`, run (cwd anywhere; paths are absolute via `-C`):
   - `git -C ~/.claude/skills/coding-team log main..<branch> --oneline` — commits unique to the branch.
   - `git -C ~/.claude/skills/coding-team diff main...<branch> --stat` — files touched + size.
   - Check whether the work already landed on main under a different SHA: read the touched files on main, or `git -C ~/.claude/skills/coding-team log main --oneline --grep '<key phrase from subject>'`.
   Decide MERGE / KEEP / DROP with a one-line reason.
   **What looks broken but isn't:** `git branch --no-merged main` OVER-reports — a squash-merged branch shows as "unmerged" while its work IS on main. Never treat "unmerged" as "unique work" without checking main's contents. Do not mistake this for a regression.

2. **Present the per-branch disposition table to the user.** Delete nothing yet. The user was explicit: keep all until reviewed, merge what makes sense, no silent drops.

3. **For each MERGE branch:** sync onto latest main (`git -C ~/.claude/skills/coding-team rebase main <branch>` or a merge), open a PR (`gh -R cmillstead/coding-team pr create`), wait for CI, merge as merge-commit.
   - CI check: `gh -R cmillstead/coding-team pr checks <n>` — read `statusCheckRollup` (poll it; `--watch` reports green while jobs still run). Expect two jobs: `test (3.11)`, `test (3.12)`.
   - If the merge changes coding-team files, bump the `~/.claude` submodule pointer per the two-repo flow (see Decisions). **This bump belongs to a `~/.claude`-rooted window** per `feedback_session-root-is-the-scope-boundary`; only run it from a coding-team session if the user says so.

4. **Only after the user signs off on drops**, `git -C ~/.claude/skills/coding-team branch -D <branch>` the DROP set. Report which ones and note reflog recovery is available ~90 days.

## Decisions made this session (with canonical homes)
- **Keep-all, review-each, no force-delete** (the branch task itself) → home: this handoff + tracker **TRK-170** (coding-team chore).
- **Two-repo ship flow** (coding-team PR → `~/.claude` submodule pointer bump via branch+PR; `gh merge` never moves local; direct-to-`~/.claude`-main is hook-blocked) → home: memory `feedback_coding-team-two-repo-ship-flow.md` + vault `2026-08-22-process-rules-gates-shipped.md`.

## Blockers / paused
- Review is **paused pending /compact** — the only reason it hasn't started. No technical blocker.

## Completed this session (context, do not redo — verified against repo)
- Process-rules gates shipped: coding-team PR #154 (`17eb69d`) + submodule pointer bump claude-harness PR #140.
- `/save` done: memory `feedback_coding-team-two-repo-ship-flow.md`, vault `2026-08-22-process-rules-gates-shipped.md`, engram synced (node #21878, 2 edges), interventions rows 49–52 written — all verified on disk.
- 41 merged local branches deleted.

## Related
- `feedback_coding-team-two-repo-ship-flow` (memory)
- `2026-08-22-process-rules-gates-shipped` (vault)
- `feedback_session-root-is-the-scope-boundary` (memory)
- tracker: TRK-031 (ci-watch), TRK-136 (git global options)
