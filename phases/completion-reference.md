# Completion Reference

On-demand detail extracted from `phases/completion.md`.

## Decision Log

- **Effective Trivial:** SKIP the decision-log prompt. The matrix specifies "SKIP at Trivial." Proceed to Session Complete.
- **Effective Small/Medium/Large:** Offer the decision log below.

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
