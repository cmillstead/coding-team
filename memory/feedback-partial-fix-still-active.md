---
name: Partial fix rationalization — batch template needed
description: Harness-engineer offers to fix a subset of findings despite completionist identity; fixed by adding explicit batch action template that covers ALL findings
type: feedback
---

The harness-engineer presents all findings in the table (completionist identity works for reporting), but then offers to route only a subset through /coding-team (completionist identity fails at the action step). Example: "Want me to route F4, F8, F1, and F12 through /coding-team?" — offering 4 of 12.

**Why:** The instruction said "never suggest partial fixes" (prohibition) but didn't say what TO do instead. The agent defaulted to cherry-picking because it had no replacement behavior template.

**How to apply:**
- Added batch action template to ct-harness-engineer.md: 6 or fewer → "I'll fix all N"; 7+ → "I'll fix all N in priority-ordered batches"
- Key framing: NEVER end with "Want me to route [subset]?" — this is the selective-fix rationalization wearing a question mark
- Prohibition alone doesn't work — you must provide the replacement behavior
- Verified: previous fix (completionist identity from cycle 11) fixed reporting but not the action step
