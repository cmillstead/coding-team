---
name: Consolidated behavioral rules
description: Distilled rules from all feedback files — load this instead of individual files
type: feedback
---

# Behavioral Rules (consolidated)

1. Dispatch agent work BEFORE doing self-executable tasks (memory saves, doc writes). Agent work takes longer.
2. NEVER suggest /ship — always suggest /release. Same for /retrospective not /retro, /doc-sync not /document-release.
3. NEVER write code directly. ALL code changes go through /coding-team. The thought "this is too simple" is the signal to use /coding-team.
4. "Pre-existing" is never a reason to skip. Fix lint warnings in modified files. Fix test failures before starting.
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
