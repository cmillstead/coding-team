---
name: coding-team-as-submodule introduces a second, distinct drift class (pinning, not copy-drift)
description: skills/coding-team is a git submodule of the claude-harness superproject; local hook edits that aren't committed to coding-team AND gitlink-bumped in the superproject are silently discarded by the next `git submodule update` — a durability failure mode the 2026-06-07 symlink fix does not address
type: project
---

## Context
`docs/plans/2026-06-30-hook-permission-friction-design.md` investigated a recurring user complaint ("fixes to these hooks KEEP REVERTING days later"). The 2026-06-07 deploy.sh symlink rewrite (see `2026-06-07-deploy-script-symlinks-not-copies.md`) eliminated repo-vs-deployed drift (editing `~/.claude/hooks/foo.py` IS editing the repo source, since it's a symlink) — but that fix only addresses drift WITHIN a single git checkout. It does not address a superproject/submodule relationship.

## Decision (documented as a distinct drift class — read the design doc before acting on it)
Confirmed by direct git inspection (`~/.claude/.gitmodules`, `git -C ~/.claude ls-tree HEAD skills/coding-team`, `git -C skills/coding-team rev-parse HEAD` / `origin/main`): `skills/coding-team` is a **git submodule** of the `~/.claude` superproject (repo name `claude-harness`, remote `git@github.com:cmillstead/coding-team.git`). The superproject pins the submodule to a specific commit SHA via a gitlink entry.

The failure mechanism: a hook edit made directly in the submodule working tree works immediately (thanks to the symlink deploy model) but is an **uncommitted (or committed-but-unpinned) working-tree change in a pinned submodule**. It is silently discarded by any of:
- `git submodule update` (default `--checkout` mode hard-resets the submodule working tree to the pinned SHA) — routinely run when syncing the superproject across machines or after a superproject `git pull`.
- a branch switch or `git checkout main`/`git reset` inside the submodule.
- `git submodule update --remote` (fast-forwards to `origin/main`, which may still carry the old/reverted state if the fix was never pushed).

This is confirmed NOT an automated re-removal and NOT a repeated git policy flip — history shows exactly one deliberate flip (`dd85530`, "deny-compounds Bash gate") with no oscillation, and neither of the two user LaunchAgents (`com.claude.janitor`, `com.engram.maintain`) touches git submodules or hook files.

**Durability requires a two-repo operation:** (1) commit the hook change in the `coding-team` submodule and push to `origin/main`; (2) bump the `claude-harness` superproject's gitlink to the new commit and push that too. A fix committed only in the submodule, without the superproject gitlink bump, still reverts on the next `git submodule update`.

## Alternatives Considered
- **Assume the symlink deploy fix (2026-06-07) already solved durability** — WRONG; that fix solves repo-vs-deployed-copy drift, not repo-vs-superproject-pin drift. They are different failure classes with different fixes (symlink vs. two-repo commit+push+gitlink-bump).
- **Stop pinning the submodule (always track `origin/main`)** — not decided; would trade a durability footgun for reduced reproducibility (superproject could pick up unreviewed submodule commits). Left as an open question in the source design doc, not resolved here.

## Constraints
- Applies specifically to hook changes under `~/.claude/skills/coding-team/hooks/` when made from a checkout where `coding-team` is a submodule of a pinned superproject. Does not apply to the standalone `coding-team` repo clone used for direct harness-repo work (no pinning superproject in that context).
- The source design doc (`docs/plans/2026-06-30-hook-permission-friction-design.md`) proposes a drift-detection companion (a session-start advisory or deploy.sh verification step warning when submodule HEAD ≠ superproject gitlink, or submodule has uncommitted changes under `hooks/`) — **not yet confirmed implemented**; treat as proposed, not shipped, until independently verified.

## Consequences
- Any harness-hook fix session must, as a final step, verify: (a) the coding-team submodule has no uncommitted changes under `hooks/`, (b) the submodule HEAD matches `origin/main`, and (c) the superproject's gitlink for `skills/coding-team` matches the submodule HEAD. Skipping (c) is the exact failure the user hit repeatedly.
- This decision record documents the CLASS of the problem (confirmed root cause) — it does NOT confirm the drift-detection mitigation shipped. See `docs/plans/2026-06-30-hook-permission-friction-design.md` §8 for open decisions still pending user resolution as of that doc's writing.
