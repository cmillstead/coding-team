---
name: Active orchestrator rules
description: Orchestrator-only behavioral rules not enforceable by hooks — loaded by /build at session start
type: feedback
---

# Active Orchestrator Rules

> Rules that require orchestrator judgment — no hook or rule-file can enforce these.
> Target: ≤20 rules. If a rule can be promoted to a hook, do so and remove it from here.

1. **Dispatch-first:** Dispatch agent work BEFORE doing self-executable tasks (memory saves, doc writes). Agent work takes longer; starting it immediately maximizes parallelism.
2. **Namespace routing:** NEVER suggest /ship — always /release. Same for /retrospective not /retro, /doc-sync not /document-release. Coding-team has its own equivalents.
3. **Coordination signal:** Agent teams when COORDINATION=yes (shared files, real-time dependencies). Subagents when work is provably independent.
4. **Symlink maintenance:** Update symlinks in ~/.claude/skills/ when renaming or creating standalone skills.
5. **Filesystem discovery:** List docs/plans/ directory first when resuming work — never guess filenames. After context loss, discover state by listing, not inference.
6. **Direct embedding:** Put tools directly in worker descriptions, not in Team Leader instructions. Direct > propagation through intermediaries. First-mentioned wins.
7. **CI classification:** CI failures require classification before action. Non-code failures (infra/billing/permissions) go to the user immediately — NEVER attempt code fixes.
8. **Background watcher discipline:** When a background CI watcher completes, read its output before dismissing. "Already handled" is a rationalization — read the log, then decide.
9. **Scan-fix continuity:** Do not pause for user confirmation between severity phases during scan-fix workflows. Print a progress summary, then continue automatically. User has Esc.
10. **Fix approach ordering:** When diagnosing behavioral issues, try identity framing and named rationalizations first (prompt-craft tiers 1-2). Only escalate to prohibitions and restructuring if those don't hold.
