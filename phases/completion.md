# Phase 6: Completion

After all tasks are executed and verified:

1. **Run full test suite** — independent verification required even if Phase 5 passed, because context may have been cleared between phases and additional commits may have landed (fresh output required)
2. **Run linter** — verify clean output
3. **Determine base branch:**
   ```bash
   git merge-base HEAD main 2>/dev/null || git merge-base HEAD master 2>/dev/null
   ```

4. **Pre-gate deliverable check:** Before presenting completion options, verify these deliverables exist:

| Deliverable | Check | If missing |
|-------------|-------|------------|
| All tests pass | Fresh test run output in this message | Run tests now |
| Linter clean | Fresh lint output in this message | Run linter now |
| Plan tasks complete | All tasks in plan have commits or explicit skip rationale | List gaps |
| Feature branch exists | Not on main/master | Cannot proceed — create branch first |

Produce any missing deliverables before opening the gate. Max 2 attempts per missing item, then warn the user and proceed anyway.

5. **Present options:**

```
Implementation complete. All tests pass. What would you like to do?

1. Merge back to <base-branch> locally
2. Push and create a Pull Request
3. Keep the branch as-is (I'll handle it later)
4. Discard this work

Which option?
```

6. **Execute choice:**
   - **Merge locally:** checkout base -> pull -> merge -> verify tests on merged result -> delete feature branch -> cleanup worktree if applicable
   - **Push and create PR:** push -> create PR with summary and test plan -> wait for CI (`gh pr checks --watch --fail-fast`) -> if CI fails, read logs (`gh run view --log-failed`), diagnose the failure, dispatch an implementer via Agent tool to fix, re-push, re-check. **Max 3 CI fix attempts.** If CI still fails after 3 attempts, present the user with:
     > CI still failing after 3 fix attempts. Options:
     > 1. Close PR and delete branch (`gh pr close --delete-branch`)
     > 2. Keep PR open (you handle it manually)
     > 3. Let me try a different approach
     Do NOT leave a failing-CI PR open without explicit user choice. If the user does not respond (session ending, context above 80%), close the PR and delete the branch: `gh pr close --delete-branch`. An orphan PR with failing CI generates email noise indefinitely.
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

**Persistence:** The completion summary is incorporated into the retrospective document when the user runs `/retrospective`. If the user skips the retrospective, save the completion summary as a standalone file: determine `$REPO_ROOT` via `git rev-parse --show-toplevel`, create `$REPO_ROOT/docs/retros/` if needed using Bash tool (`mkdir -p`), and write the summary to `$REPO_ROOT/docs/retros/YYYY-MM-DD-<feature-slug>-completion.md` using the Write tool. Do NOT skip saving — completion summaries contain audit patterns that inform future planning.

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

**Also persist to ContextKeep:** After writing the decision file, use `mcp__context-keep__store_memory` to store the decision with key `decision-<slug>` and the decision content as the value. This makes decisions searchable by the planning worker via `mcp__context-keep__search_memories` in future sessions. If ContextKeep is not available (MCP server not running), skip and note in status: 'ContextKeep not available — skipped' — the file-based approach is the primary record.

**If the user says no or skips**, proceed to Session Complete. Do NOT generate decisions the user didn't identify — this captures human organizational knowledge, not agent observations.

Read `phases/memory-nudge.md` and follow its instructions.

---

## Session Complete

After the user chooses a completion option and it's been executed, print this block VERBATIM (substitute actual branch name and chosen option):

> ---
>
> **Feature complete.** Branch: `<branch>` | Option: `<chosen option>`
>
> **Recommended next steps:**
>
> 1. `/retrospective` — engineering retrospective (commit patterns, test health, shipping velocity, what to improve). Saves to `docs/retros/` with eval feed-forward to `docs/project-evals.md`. Use coding-team's `/retrospective`, NOT gstack's `/retro` — they are different skills.
> 2. `/doc-sync` — update README, ARCHITECTURE, CLAUDE.md to match the shipped code
> 3. `/prompt-craft audit` — if this feature changed any skills, prompts, or CLAUDE.md, verify they still trigger correctly
>
> **If you chose "Push and create PR" and want a more automated release:** Run `/release` — it syncs main, runs tests, audits coverage, pushes, and creates the PR with coverage stats.
>
> **Starting something new?** `/clear` then `/coding-team` with your next task.
>
> ---
