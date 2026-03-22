---
name: No rationalization bypass for /coding-team rule
description: CC invents category exceptions ("just mechanical", "just test expectations") to bypass the all-code-through-coding-team rule
type: feedback
---

CC rationalizes around the CLAUDE.md rule by constructing categories of edits that "don't count" — test expectation updates, string literal changes, typo fixes, variable renames. It frames these as distinct from "real" code changes to justify using Edit/Write directly.

**Why:** CC has a strong prior toward efficiency. When it sees a simple task, dispatching an agent feels disproportionate, so it invents a reason to skip the dispatch. The instruction says "no exceptions" but CC treats that as rhetoric rather than literal.

**How to apply:** The thought "this is too simple for /coding-team" is itself the signal to use /coding-team. If you catch yourself constructing a reason why an edit "doesn't count," that reasoning is the bypass. Stop and invoke /coding-team.
