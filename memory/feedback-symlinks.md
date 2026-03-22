---
name: Update symlinks when renaming or creating skills
description: Skill renames and new skills require symlink updates in ~/.claude/skills/ — not just repo-internal file changes
type: feedback
---

When renaming a skill directory or creating new standalone skills, the symlinks in `~/.claude/skills/` must be updated in the same step. The skill doesn't work until the symlink exists.

**Why:** Renamed `codex` → `second-opinion` and created 5 new skills but only updated files inside the repo. The old symlink still pointed to gstack's codex, and the 5 new skills had no symlinks at all. User got "Unknown skill: second-opinion."

**How to apply:** Every time a skill directory is renamed, created, or deleted:
1. Check `ls -la ~/.claude/skills/<name>` for existing symlink
2. Remove stale symlink if it exists
3. Create new symlink: `ln -s ~/.claude/skills/coding-team/skills/<name> ~/.claude/skills/<name>`
4. Verify with `ls -la ~/.claude/skills/<name>`
