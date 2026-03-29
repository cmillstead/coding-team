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

Check if `/Users/cevin/.claude/skills/coding-team/memory/patterns.md` exists using the Read tool:
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
