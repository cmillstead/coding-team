**Step 1: Check if this is a continuation.** If the user mentions a phase number, task number, feature name, "continue", "pick up where I left off", or any reference to prior work — this is a **resumed session**. Go to Step 2 before routing.

**Step 1.5: Check for orphan PRs.**

Before plan discovery, check for open PRs with failing CI from this repo:

```bash
gh pr list --state open --author @me --json number,title,statusCheckRollup 2>/dev/null | jq -r '.[] | select(.statusCheckRollup != null) | select([.statusCheckRollup[].conclusion // empty] | any(. == "FAILURE")) | "#\(.number): \(.title)"'
```

If any found, print:

> **Open PRs with failing CI:**
> - [list each]
>
> Clean up? **close** (close PR + delete branch) / **fix** (investigate and fix) / **ignore** (proceed, you handle it)

- close: run `gh pr close N --delete-branch` for each
- fix: route to `/coding-team` to investigate CI failures before resuming the original task
- ignore: proceed with the user's original request

If none found or `gh` is not available, proceed and note: 'No orphan PRs detected.'

**Step 2: Discover existing plans and detect progress.** You have NO memory of prior conversations. Do NOT guess filenames.

Plans live in the **main repo**, not in worktrees. Find the repo root first:

```bash
# Get the main repo root (not a worktree)
MAIN_ROOT=$(git rev-parse --path-format=absolute --git-common-dir | sed 's/\/.git$//')
```

Then search for plans there:

```
Glob $MAIN_ROOT/docs/plans/*.md
```

- **No docs/plans/ directory or no .md files:** Check for a state file at `$MAIN_ROOT/docs/plans/.coding-team-state`. If it exists, read it — the user approved an approach but hasn't reached the spec stage yet. Resume at Phase 2. If no state file either, this is a fresh task. Route using the table below.
- **Files found:** Read each file's first 10 lines (title/header). If a plan file is empty, truncated, or has no `## Tasks` section: report 'Plan file [name] appears corrupt — [issue]' and ask user how to proceed. Match the user's request to a plan by content, not filename. If ambiguous, show the user the list and ask which one.

**If you are in a worktree:** the plan files will NOT be in your current directory. Always resolve back to the main repo root to find them. Pass the full path to plan files when providing context to implementers.

**Progress detection (for continuation sessions):**

After finding a matching plan, determine where the user left off:

```
1. Read the plan file to get the full task list
2. Check git log for commits matching each task:
   - Match by task name/description in commit message
   - Match by files listed in the task appearing in recent commits
3. Determine: last completed task number, next incomplete task number
4. Check current test state: run the project's test suite (or check last known result)
5. Print the recovery block (see format below)
```

**Recovery block format** — print this VERBATIM when resuming (substitute actual values):

> ---
> **Resuming:** <feature name from plan title>
>
> **Branch:** `<current branch>`
> **Plan:** `<path to plan file>`
> **Phase:** <detected phase> (<phase name>)
> **Progress:** <Tasks 1-N of M complete (last commit: <short sha> <message>)> OR <No tasks started yet>
> **Next:** <Task N+1: <task name>> OR <Phase action>
> **Tests:** <All passing | N failures | not yet checked>
>
> Ready to continue? Proceed?
> ---

**Recovery heuristics by clear point:**

| What's on disk | Recovery action |
|---|---|
| `.coding-team-state` only (no spec, no plan) | Resume at Phase 2 (design team) |
| Design spec (`*-design.md`) but no plan | Resume at Phase 4 (planning) |
| Plan file, no task commits on feature branch | Resume at Phase 5, Task 1 |
| Plan file + N task commits | Resume at Phase 5, Task N+1 |
| Plan file + all tasks committed | Resume at Phase 6 (completion) |
| Plan file + merged/PR'd branch | Feature looks done — inform user |

**Step 2.5: Context Refresh (continuation sessions only)**

When resuming a session (detected in Step 1), check what changed since the last activity:

1. Compute hours since last commit on the feature branch:
   ```bash
   HOURS_SINCE=$(( ($(date +%s) - $(git log -1 --format="%ct" HEAD)) / 3600 ))
   ```

2. If `HOURS_SINCE` is greater than 24:
   a. Check for commits on the base branch since the branch diverged:
      ```bash
      git log --oneline $(git merge-base HEAD main)..origin/main
      ```
   b. If commits found, print this context refresh:
      > **Context refresh:** N commits landed on main since your last session.
      > [one-line summary of key changes]
      >
      > Any of these affect our work? (If unsure, I'll proceed.)
   c. Wait for user response before routing to Step 3.
   d. If no commits found on the base branch, proceed directly to Step 3.
   e. If the project has a `memory/decisions/` directory, check for new decision entries on main since the branch point:
      ```bash
      git log --diff-filter=A --name-only --format="" $(git merge-base HEAD main)..origin/main -- "memory/decisions/"
      ```
      If new decisions found, read them and include in the context refresh report.

3. If `HOURS_SINCE` is 24 or less, skip this step — proceed directly to Step 3.

After completing these steps, return to SKILL.md and proceed to **Step 3: Route.**
