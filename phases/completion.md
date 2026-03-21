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
   - **Push and create PR:** push -> create PR with summary and test plan
   - **Keep as-is:** report branch name and worktree path, done
   - **Discard:** require user to type "discard" to confirm -> delete branch -> cleanup worktree

**Never** proceed with failing tests, merge without verifying, delete work without confirmation, or dismiss pre-existing test failures as "not our problem."

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

---

## Session Complete

After the user chooses a completion option and it's been executed, print this block VERBATIM (substitute actual branch name and chosen option):

> ---
>
> **Feature complete.** Branch: `<branch>` | Option: `<chosen option>`
>
> **Recommended next steps:**
>
> 1. `/retro` — engineering retrospective (commit patterns, test health, shipping velocity, what to improve)
> 2. `/document-release` — update README, ARCHITECTURE, CLAUDE.md to match the shipped code
> 3. `/prompt-craft audit` — if this feature changed any skills, prompts, or CLAUDE.md, verify they still trigger correctly
> 4. If PR'd: check CI/CD pipeline status
>
> **If you chose "Push and create PR" and want a more automated release:** Run `/ship` — it syncs main, runs tests, audits coverage, pushes, and creates the PR with coverage stats.
>
> **Starting something new?** `/clear` then `/coding-team` with your next task.
>
> ---
