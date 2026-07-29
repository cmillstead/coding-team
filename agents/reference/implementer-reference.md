# Implementer Reference

On-demand sections loaded when relevant. The main agent file (`ct-implementer.md`) references these.

## Code Exploration

Use `mcp__codesight__query` to understand the codebase before writing code. Pass `operation` (kebab-case) and `params` (camelCase object):

| Operation | When to use | Example params |
|-----------|-------------|----------------|
| `search-symbols` | Before creating new utilities — check if one exists | `{query: "MyUtil", repo: "my-repo"}` |
| `get-callers` | Before modifying a function — find all call sites | `{repo: "my-repo", symbolId: "abc123"}` |
| `get-file-outline` | Understand file structure before editing | `{repo: "my-repo", filePath: "src/foo.py"}` |
| `get-call-chain` | Trace data flow through a codepath you're modifying | `{repo: "my-repo", fromSymbol: "callerFunc", toSymbol: "calleeFunc"}` |
| `get-symbol` | Read a specific function/class without loading the full file | `{repo: "my-repo", symbolId: "abc123"}` |

If `mcp__codesight__query` returns a connection error, timeout, or API error: do NOT retry it. Mark the tool unavailable for this session and fall back to Grep/Read for that specific query. Known rationalization: "maybe it's back up now" — it isn't. One retry is the maximum.

Additional context (GitHub issues, dependency analysis, LSP diagnostics) is pre-computed by the orchestrator and included in your task context when relevant.

## Pre-fix RED evidence

Required field in every DONE report. One entry per new-or-modified test, each using EXACTLY ONE of these four branches:

1. `RED: <test id>` followed by the verbatim failing assertion and error line, captured BEFORE the fix. Verbatim means copied from the actual run — not a paraphrase, not a description, not post-fix output.
2. `BASELINE-GREEN: <test id> — <reason>` — the test legitimately passes before the fix because it pins behavior the change must NOT break (preservation/invariant test).
3. `CANNOT-FAIL: <test id> — <reason>` — you could not construct a pre-fix state in which it fails. This IS a finding: report `DONE_WITH_CONCERNS`. Do not silently keep the test.
4. `NO-TEST-CHANGES: <reason>` — this task added and modified zero test files.

Coverage rule: every changed behavior needs at least 1 `RED:` entry. A report that changes behavior and carries only `BASELINE-GREEN:` entries is a FAIL — go back and capture the RED.

Known rationalization: "the test obviously would have failed" — an assertion you did not run produced no output, and a field with no output is an empty field. Run it before the fix or use branch 3.

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
