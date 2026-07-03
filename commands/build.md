---
name: build
description: Orchestrate code tasks through a specialist agent team — design, plan, execute, verify, ship
argument-hint: "[request | plan <request> | execute <plan-file> | auto <request> | continue]"
---

# /build — Alias for the /coding-team Pipeline

`/build` is a thin slash-command alias for the `/coding-team` skill. It carries no
independent phase logic, gate rules, or agent lists of its own.

**To execute this command:**

1. Read `~/.claude/skills/coding-team/SKILL.md`.
2. Follow its Session Start router and Phase Sequence exactly, reading each
   `~/.claude/skills/coding-team/phases/*.md` detail file on entry as instructed there.
3. Pass `$ARGUMENTS` through unchanged as the user's request/entry-point
   selector (e.g. `plan <request>`, `execute <plan-file>`, `auto <request>`,
   `continue`).

Do not duplicate phase content, routing tables, red flags, or edit-routing
rules here — `SKILL.md` and `phases/` are the single source of truth. If this
file and `SKILL.md` ever disagree, `SKILL.md` wins.
