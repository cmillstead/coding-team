---
name: scope-unlock
description: Remove the active /scope-lock edit restriction
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
