---
name: Don't pause between phases
description: User prefers auto-continue between severity phases in scan-fix and similar workflows — no "Continue?" prompts
type: feedback
---

Do not pause for user confirmation between severity phases during scan-fix or other multi-phase workflows. Print a progress summary between phases, then continue automatically.

**Why:** The user has Esc to interrupt if needed. Mandatory pauses add friction without value — the user is watching the output and will intervene when necessary.

**How to apply:** Phase transitions should print a summary (what completed, what's next) then proceed immediately. Only pause for the initial "Proceed?" before starting work, or when a finding requires a design decision (line 62 of scan-fix: "Finding requires design decision: Stop and ask the user").
