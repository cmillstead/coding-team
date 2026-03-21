---
name: worktree
description: "Use when the user requests an isolated workspace, or when the task modifies 5+ files across 3+ directories. Do NOT suggest for single-file changes, typo fixes, or when the user says to work in-place."
---

# /worktree — Isolated Feature Workspace

When invoked standalone:
- If the user provides a feature/branch name, use it
- If not, ask: "What are you working on? (used for branch naming)"
- After setup, report the worktree path and baseline test status

When invoked from /coding-team Phase 5, the lead provides the feature name. Skip the above.

---

## When to Use

- Before executing an implementation plan (Phase 5)
- Any feature work that benefits from isolation
- When the user explicitly requests a worktree

Skip when: trivial bug fixes, single-file changes, or user says to work in-place.

## Directory Selection (priority order)

1. **Check existing:** `ls -d .worktrees worktrees 2>/dev/null` — if found, use it (`.worktrees` wins if both exist)
2. **Check CLAUDE.md:** `grep -i "worktree.*director" CLAUDE.md 2>/dev/null` — use if specified
3. **Ask user:**
   > No worktree directory found. Where should I create worktrees?
   > 1. `.worktrees/` (project-local, hidden)
   > 2. `~/.config/worktrees/<project-name>/` (global location)

## Safety: Verify Ignored

For project-local directories, verify the directory is gitignored BEFORE creating:

```bash
git check-ignore -q .worktrees 2>/dev/null
```

If NOT ignored: add to `.gitignore`, commit, then proceed.

## Creation Steps

```bash
# 1. Detect project name
project=$(basename "$(git rev-parse --show-toplevel)")

# 2. Create worktree with new branch
git worktree add "$path" -b "$BRANCH_NAME"
cd "$path"

# 3. Auto-detect and run setup
[ -f package.json ] && npm install
[ -f Cargo.toml ] && cargo build
[ -f requirements.txt ] && pip install -r requirements.txt
[ -f pyproject.toml ] && uv sync 2>/dev/null || poetry install
[ -f go.mod ] && go mod download

# 4. Verify clean baseline
# Run project test suite — report if tests fail, ask whether to proceed
```

## Report

```
Worktree ready at <full-path>
Tests passing (<N> tests, 0 failures)
Ready to implement <feature-name>
```

## Plan Files

Plan and design docs (`docs/plans/*.md`) live in the **main repo root**, not in worktrees. When resuming work in a worktree, resolve the main repo root to find plans:

```bash
MAIN_ROOT=$(git rev-parse --path-format=absolute --git-common-dir | sed 's/\/.git$//')
ls "$MAIN_ROOT/docs/plans/"
```

Always pass full paths to plan files when providing context to implementers working in a worktree.

## Cleanup

After work is complete (Phase 6), cleanup depends on the completion choice:
- **Merge locally or Discard:** `git worktree remove <path>`
- **Push/PR or Keep:** leave worktree in place
