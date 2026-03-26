---
name: scope-unlock
description: "Remove a /scope-lock edit restriction (coding-team pipeline). For removing a /freeze restriction, use /unfreeze instead."
---

# /scope-unlock — Remove Edit Restriction

Clear the scope-lock boundary set by `/scope-lock`. Edits are allowed to all directories again.

## Usage

```
/scope-unlock
```

## Behavior

1. Clear the active scope-lock boundary.
2. Print: "Scope lock removed. Edits allowed to all directories."
3. If no scope-lock was active, print: "No scope lock active."

## When to Use

- After `/debug` investigation completes and the fix is verified
- When you need to edit files outside the locked directory
- When resuming normal execution after a debugging detour
