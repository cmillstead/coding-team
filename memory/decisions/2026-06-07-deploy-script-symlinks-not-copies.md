---
name: deploy.sh rewritten to relative symlinks (not copies)
description: deploy() now creates relative symlinks (ln -sfn) instead of cp; drift between repo source and deployed ~/.claude/ artifacts is now structurally impossible, not just detected
type: project
---

## Context
The 2026-03-25 decision (`2026-03-25-deploy-script-eliminates-drift.md`) introduced `scripts/deploy.sh` as the canonical deployment mechanism, but it worked by **copying** files from the repo into `~/.claude/`. Copying still allowed drift: a deployed copy could be hand-edited (or left stale after a repo change) without deploy.sh re-running, and the `track-artifacts-in-repo.py` hook could only detect drift reactively, after the fact. The 2026-06-06 hook-outage retro (`docs/retros/2026-06-06-agent-hook-outage-fix.md`) reconfirmed the class recurred inside the fix for an unrelated bug — an implementer edited the deployed tree instead of source.

## Decision
Rewrote `deploy()` in `scripts/deploy.sh` (PR #69, commit `8fbad9a`, 2026-06-07) to create **relative symlinks** (`ln -sfn`) from `~/.claude/{hooks,agents,rules}/...` back to the repo source, instead of copying file contents. `hooks/_lib/` is symlinked as one directory unit rather than per-file. `rules/` deploys every `*.md` except `README.md` (which is deploy meta-doc, not a behavioral rule) as a symlink into `~/.claude/rules/`.

## Alternatives Considered
- **Keep copying + rely on drift detection** — rejected: detection is reactive (fires after the bad state already exists) and depends on a hook actually running before the stale copy is used; a symlink makes the bad state impossible to reach.
- **Copy + pre-commit/pre-deploy hash check** — rejected: extra moving part, still allows a window where deployed and source diverge between check runs.

## Constraints
- macOS-safe: relative path computed via `python3 -c os.path.relpath` (no GNU-only `realpath --relative-to`).
- `hooks/_lib/` must be removed first if it exists as a real (non-symlink) directory, so `ln -sfn` can place the directory symlink.
- `scripts/deploy.sh` also verifies every deployed hook is registered in `settings.json` or one of the two dispatchers (`prompt-dispatcher.py`, `session-start-dispatcher.py`) — later extended to `pretooluse-dispatcher.py`/`posttooluse-dispatcher.py` registration sites (D198, commit `00652cf`).

## Consequences
- Editing the deployed path (`~/.claude/hooks/foo.py`) now edits the SAME inode as the repo source — there is no longer a "deployed copy" to drift from source.
- The remaining drift vector is **repo-vs-git-remote** drift when the repo itself is a submodule pinned by a superproject (see `2026-06-30-hook-permission-friction-design.md` — this is a DIFFERENT drift class, addressed separately; see the repo-as-submodule decision record).
- `docs/retros/2026-06-06-agent-hook-outage-fix.md`'s lesson ("edit source not deployed, for hooks") is now partially enforced structurally — hand-editing the deployed path IS editing source, by construction — but still requires the editor to run `deploy.sh` at least once for NEW files (new top-level hooks, new agents) since the symlink itself must be created.

**Superseded:** `2026-03-25-deploy-script-eliminates-drift.md` is superseded by this record for the deployment MECHANISM (copy → symlink). Its rationale for WHY a single deployment mechanism matters (Case 28 recurrence) still stands.
