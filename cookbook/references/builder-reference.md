# Builder Reference

On-demand sections loaded when relevant. The main agent file (`ct-builder.md`) references these.

## Code Exploration

Use codesight-mcp tools to understand the codebase before writing code:

| Tool | When to use |
|------|-------------|
| `search_symbols` | Before creating new utilities — check if one exists |
| `get_callers` | Before modifying a function — find all call sites |
| `get_file_outline` | Understand file structure before editing |
| `get_call_chain` | Trace data flow through a codepath you're modifying |
| `get_symbol` | Read a specific function/class without loading the full file |

All tool names above are prefixed `mcp__codesight-mcp__` when calling.

If ANY codesight-mcp tool call returns a connection error, timeout, or API error: do NOT retry it. Mark the tool unavailable for this session and fall back to Grep/Read for that specific query. Known rationalization: "maybe it's back up now" — it isn't. One retry is the maximum.

Additional context (GitHub issues, dependency analysis, LSP diagnostics) is pre-computed by the orchestrator and included in your task context when relevant.

## CI Fix Context

Expected fields from orchestrator:
- **Failing CI step:** [step name from the CI run]
- **Error output:** [VERBATIM log — the orchestrator pastes the full output]
- **Files mentioned:** [files and lines from the error]
- **Prior attempts:** [what was already tried, if retry 2 or 3]

Your job: reproduce the failure locally FIRST. Run the exact command that
failed in CI. Do NOT guess at the fix from the error message alone.

If the failure cannot be reproduced locally, report BLOCKED with:
- What you ran locally and its output
- The CI error output for comparison
- Your hypothesis for why they differ (OS, Node/Python version, env vars)

## When You're in Over Your Head

It is always OK to stop and say "this is too hard for me." Bad work is worse
than no work. You will not be penalized for escalating.

**STOP and escalate when:**
- The task requires architectural decisions with multiple valid approaches
- You need to understand code beyond what was provided
- You feel uncertain about whether your approach is correct
- You've been reading file after file without progress

**How to escalate:** Report with status BLOCKED or NEEDS_CONTEXT.
