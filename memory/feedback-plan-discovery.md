---
name: Plan discovery on session resume
description: When resuming multi-phase work after context clear, list docs/plans/ directory first — never guess filenames
type: feedback
---

When resuming a multi-phase task after clearing context, always list `docs/plans/` first to discover what exists. Never guess or construct filenames based on the user's description of the phase.

**Why:** User split phase 7 into 7a/7b/7c. After completing 7b, they saved memory and cleared context. Starting 7c, the skill couldn't find plan files. When pointed to docs/plans, it searched for specific .md filenames by name instead of listing what was there. Required two corrections before it found the plans.

**How to apply:** Any time a conversation starts mid-task or the user references continuing prior work, the first action must be `ls docs/plans/` or `Glob docs/plans/*.md` — discover by listing, then match by reading content. Never construct expected filenames from phase numbers or feature names.
