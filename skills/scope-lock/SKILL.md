---
name: scope-lock
description: "Restrict file edits to a specific directory within the coding-team pipeline. Prevents accidentally modifying unrelated code while debugging. Run /scope-unlock to remove. For standalone edit restriction outside coding-team, use /freeze."
---

# /scope-lock — Restrict Edits to a Directory

Lock edits to a specific directory for the rest of the session. The Edit and Write tools will only operate on files within the locked path. All other paths are blocked until `/scope-unlock` is run.

## Usage

```
/scope-lock <directory>
```

Example: `/scope-lock src/cache/` restricts all edits to files under `src/cache/`.

## When to Use

- During `/debug` investigation — prevents fixing unrelated code while hunting a root cause
- When a task owns a specific module — scope edits to that module
- When touching production-critical code — limit blast radius

## Behavior

1. Record the locked directory path (resolve to absolute path via `git rev-parse --show-toplevel`).
2. Before every Edit or Write tool call for the rest of the session, check:
   - Is the target file path within the locked directory?
   - If YES: proceed with the edit.
   - If NO: block the edit. Print: "Edit blocked — outside scope-lock boundary (`<locked-dir>`). Run `/scope-unlock` to remove the restriction."
3. Read tool calls are NOT restricted — you can read any file for context.
4. Bash tool calls are NOT restricted — you can run any command.

## Scope Lock is Advisory

This is an instruction-level restriction, not a filesystem permission. It works because the skill tells CC to check before editing. If CC ignores the check under context pressure, the restriction fails silently.

To strengthen: the mid-phase execution reminder re-asserts the scope lock if one is active.

## Multiple Locks

Only one scope-lock is active at a time. Running `/scope-lock <new-dir>` replaces the previous lock. To remove without replacing, use `/scope-unlock`.

## Red Flags

- Do NOT scope-lock to the repo root — that locks nothing.
- Do NOT scope-lock to a path that doesn't exist — resolve and verify first.
- Do NOT forget to `/scope-unlock` after debugging — the lock persists until removed.
