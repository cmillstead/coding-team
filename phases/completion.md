# Phase 6: Completion

After all tasks are executed and verified:

1. **Run full test suite** — verify everything passes (fresh output required)
2. **Run linter** — verify clean output
3. **Determine base branch:**
   ```bash
   git merge-base HEAD main 2>/dev/null || git merge-base HEAD master 2>/dev/null
   ```

4. **Present options:**

```
Implementation complete. All tests pass. What would you like to do?

1. Merge back to <base-branch> locally
2. Push and create a Pull Request
3. Keep the branch as-is (I'll handle it later)
4. Discard this work

Which option?
```

5. **Execute choice:**
   - **Merge locally:** checkout base -> pull -> merge -> verify tests on merged result -> delete feature branch -> cleanup worktree if applicable
   - **Push and create PR:** push -> create PR with summary and test plan -> wait for CI (`gh pr checks --watch --fail-fast`) -> if CI fails, read logs (`gh run view --log-failed`), fix via `/coding-team`, re-push, re-check. Do NOT leave a PR with failing CI.
   - **Keep as-is:** report branch name and worktree path, done
   - **Discard:** require user to type "discard" to confirm -> delete branch -> cleanup worktree

**Never** proceed with failing tests, merge without verifying, delete work without confirmation, or dismiss failures/findings as "pre-existing" or "not our problem." A bug is a bug regardless of when it was introduced.

## Learning Loop (Completion Summary)

After all tasks, produce a summary that includes audit findings across all rounds:

```
## Completion Summary

**Audit rounds:** N of 3 max
**Exit reason:** clean audit | low-only round | loop cap

### Recurring patterns
- [pattern]: appeared N times across rounds, severity, resolution
- [pattern]: ...

### Unresolved (low severity, deferred)
- [finding]: reason deferred

### Out-of-scope observations
- [anything auditors flagged outside the task scope]
```

Recurring patterns are the signal — if the same finding type appears across multiple tasks or rounds, it indicates a systemic issue worth noting for future work.

## Decision Log

After producing the completion summary, check whether any architectural or design decisions were made during this feature that should be recorded for future sessions.

**Prompt the user:**

> Were any architectural or design decisions made during this feature? (e.g., "chose X over Y because Z", "this API uses polling not webhooks because...", "we keep the old table for backward compat until...")
>
> If yes, I'll write a decision record to `memory/decisions/`.

**If the user provides decisions**, write each to `memory/decisions/YYYY-MM-DD-<slug>.md` using the Write tool:

```markdown
---
name: [decision title]
description: [one-line summary]
type: project
---

## Context
[What situation prompted this decision]

## Decision
[What was chosen]

## Alternatives Considered
- [Alternative] — rejected because [reason]

## Constraints
[Organizational, technical, or relationship factors]

## Consequences
[What would break if reversed without understanding why]
```

**If the user says no or skips**, proceed to Session Complete. Do NOT generate decisions the user didn't identify — this captures human organizational knowledge, not agent observations.

---

## Session Complete

After the user chooses a completion option and it's been executed, print this block VERBATIM (substitute actual branch name and chosen option):

> ---
>
> **Feature complete.** Branch: `<branch>` | Option: `<chosen option>`
>
> **Recommended next steps:**
>
> 1. `/retrospective` — engineering retrospective (commit patterns, test health, shipping velocity, what to improve). Use coding-team's `/retrospective`, NOT gstack's `/retro` — they are different skills.
> 2. `/doc-sync` — update README, ARCHITECTURE, CLAUDE.md to match the shipped code
> 3. `/prompt-craft audit` — if this feature changed any skills, prompts, or CLAUDE.md, verify they still trigger correctly
>
> **If you chose "Push and create PR" and want a more automated release:** Run `/release` — it syncs main, runs tests, audits coverage, pushes, and creates the PR with coverage stats.
>
> **Starting something new?** `/clear` then `/coding-team` with your next task.
>
> ---
