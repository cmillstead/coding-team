---
name: Consolidated behavioral rules
description: Distilled rules from all feedback files — load this instead of individual files
type: feedback
---

# Behavioral Rules (consolidated)

1. Dispatch agent work BEFORE doing self-executable tasks (memory saves, doc writes). Agent work takes longer.
2. NEVER suggest /ship — always suggest /release. Same for /retrospective not /retro, /doc-sync not /document-release.
3. NEVER write code directly. ALL code changes go through /coding-team. The thought "this is too simple" is the signal to use /coding-team.
4. "Pre-existing" is never a reason to skip. Fix lint warnings in modified files. "Only warnings, no errors" is NOT a reason to skip — warnings are defects.
5. NEVER commit to main/master. Always use feature branches + PRs.
6. Agents silently drop findings — require completeness gates. count(inputs) must equal count(outputs).
7. Main agent is the orchestrator in Phase 5. NEVER use Edit/Write/Bash for tests directly.
8. Agent teams when COORDINATION=yes. Subagents when independent work.
9. Use /prompt-craft audit before writing or modifying skill instructions.
10. Update symlinks in ~/.claude/skills/ when renaming or creating standalone skills.
11. List docs/plans/ directory first when resuming work — never guess filenames.
12. Direct embedding > propagation through intermediaries. Put tools in worker descriptions, not Team Leader instructions.
13. Codesight-mcp is preferred for code analysis when available. Reindex stale indexes. Grep/Read are fallbacks when MCP is unavailable or calls fail.
14. CI failures require classification before action. Non-code failures (infra/billing/permissions) go to the user immediately — NEVER attempt code fixes.
15. When a background CI watcher completes, read its output before dismissing. "Already handled" is a rationalization — read the log, then decide.
16. Re-read files immediately before editing if the user may have modified them externally. Do not rely on stale reads from earlier in the conversation.
17. Never retry a failed MCP tool more than once. Mark it unavailable for the session, degrade to built-in tools (Glob, Grep, Read). "Maybe it's back up now" — it isn't.
18. Chunk large taxonomy/disambiguation work into clusters of 5-8 items per agent call. Never process 30+ items in a single context window — compaction loses precision.
19. Run multi-pass audits with distinct focus per pass: (1) agent-internal, (2) cross-file consistency, (3) behavioral executability, (4) migration residue. Stop when a pass comes back clean.
20. Track agents and hooks in their team repo, not just ~/.claude/. Repo copies are source of truth; ~/.claude/ copies are runtime deployment.
21. Use identity framing ("you are the orchestrator") over prohibition ("NEVER write code") for behavioral shaping. Reserve prohibition for safety rails only.
22. Subagent prompts must explicitly override inherited CLAUDE.md rules that conflict with the subagent's role. Agents cannot infer exemptions from context.
23. Pre-compute external intelligence (dep audit, secret scanning, CVE search) at the orchestrator level before dispatching workers. Workers under context pressure skip external tool calls.
24. Keep skill files under 200 lines. Extract workers to workers/ dirs and phases to phases/ dirs, loaded on demand. Context saturation defeats MANDATORY labels beyond this threshold.
25. Check for dark features after implementation: exported functions with zero external callers, routes defined but not registered, event handlers declared but not subscribed.
26. Do not pause for user confirmation between severity phases during scan-fix workflows. Print a progress summary, then continue automatically. User has Esc to interrupt.
27. When diagnosing behavioral issues, try identity framing and named rationalizations first (prompt-craft tiers 1-2). Only escalate to prohibitions and restructuring if those don't hold.
