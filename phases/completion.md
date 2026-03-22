# Phase 6: Completion

After all tasks are executed and verified:

1. **Run full test suite** — independent verification required even if Phase 5 passed, because context may have been cleared between phases and additional commits may have landed (fresh output required)
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

**Also persist to ContextKeep:** After writing the decision file, use `mcp__context-keep__store_memory` to store the decision with key `decision-<slug>` and the decision content as the value. This makes decisions searchable by the planning worker via `mcp__context-keep__search_memories` in future sessions. If ContextKeep is not available (MCP server not running), skip silently — the file-based approach is the primary record.

**If the user says no or skips**, proceed to Session Complete. Do NOT generate decisions the user didn't identify — this captures human organizational knowledge, not agent observations.

## Memory Nudge

After the decision log (whether the user provided decisions or skipped), extract and persist learnings from this session. Three outputs: project-local facts, cross-project patterns, and a vault episode.

### Step 1: Extract codebase facts

Review the session for facts discovered about this specific project's codebase — schema shapes, auth patterns, API contracts, module boundaries, configuration quirks, performance characteristics.

Check if `docs/team-memory.md` exists in the project repo using the Read tool:
- **If it exists:** Read it. Identify new facts not already captured.
- **If it doesn't exist:** Create it using the Write tool with this template:

````markdown
# Team Memory

> Auto-maintained by coding-team. Reviewed by human.
> Max 10 entries per section. When full, oldest entries rotate to docs/team-memory-archive.md.

## Codebase Facts
- [fact]: [context/evidence] (discovered YYYY-MM-DD)

## Known Landmines
- [landmine]: [why it's dangerous] (discovered YYYY-MM-DD)

## Project Patterns
- [pattern]: [when it applies] (discovered YYYY-MM-DD)
````

**Rotation rule:** When any section reaches 10 entries and a new entry needs to be added:
1. Read (or create) `docs/team-memory-archive.md` using the Read/Write tools
2. Move the oldest entry to the archive with a `[archived YYYY-MM-DD]` prefix
3. Add the new entry to team-memory.md

Do NOT delete rotated entries. Archived facts may become relevant again.

### Step 2: Extract cross-project patterns

Review the completion summary's "Recurring patterns" section. If any pattern is general enough to apply across projects (not specific to this codebase), add it to coding-team's own memory.

Check if `/Users/cevin/.agents/skills/coding-team/memory/patterns.md` exists using the Read tool:
- **If it exists:** Read it. Only add patterns not already captured.
- **If it doesn't exist:** Create it using the Write tool with frontmatter:

````markdown
---
name: Cross-project recurring patterns
description: Patterns discovered across multiple projects that inform future design and review — auto-maintained by completion phase
type: feedback
---

# Recurring Patterns

- [pattern]: [evidence from N projects] (first seen YYYY-MM-DD)
````

Only add a pattern to cross-project memory if it appeared in 2+ sessions or is clearly universal (e.g., "migration PRs always need schema DDL verification"). Do NOT add project-specific observations.

### Step 3: Write structured episode to vault

Write a structured episode using the Write tool to `~/Documents/obsidian-vault/AI/context/patterns/episodes/YYYY-MM-DD-<feature-slug>.md`:

````markdown
# Episode: <Feature Name> (YYYY-MM-DD)
> Part of [[coding-team-episodes]]

**Project:** <project name>
**Branch:** `<branch>`
**Scope:** <1-2 sentence description of what was built/fixed>

## What Happened
- <key event 1 — what was attempted, what was found>
- <key event 2>
- <key event 3>

## Decisions Made
- <decision>: <rationale>

## Patterns Discovered
- <pattern>: <when it applies>

## What Would Help Next Time
- <improvement or thing to check earlier>

## Related
- [[<previous related episode if any>]]
````

Write the episode description to be **pattern-rich, not keyword-specific.** The description should capture the underlying pattern so that QMD vector_search can match it to future situations with different surface details. For example:

- BAD: "Fixed bug in edges.explanation route" (keyword-specific, won't match future schema drift)
- GOOD: "Code referenced database schema columns that didn't exist yet — discovered when route handler queried a column added in a migration that hadn't been applied" (pattern-rich, matches any schema drift scenario)

### Step 4: Present for review

Print the extracted items to the user:

```
## Memory Nudge

**Codebase facts** (→ docs/team-memory.md):
- [fact 1]
- [fact 2]

**Cross-project patterns** (→ memory/patterns.md):
- [pattern 1] (or "None — no new cross-project patterns")

**Episode** (→ vault):
- [episode title and 1-line summary]

Save these? (Y/n — or edit any before saving)
```

If the user approves, write all three using the Write tool. If the user edits, apply edits then write. If the user declines, skip — do NOT persist without approval.

**Future sessions:** Once the user has approved 3+ memory nudges without edits, add a note: "You've approved N memory nudges. Want me to auto-save going forward? (You can always review in the files.)" If they say yes, skip the review prompt in future sessions and save directly.

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
