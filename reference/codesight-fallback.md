<!-- Loading is determined by DIRECTORY, not frontmatter. Frontmatter is inert:
     anything under ~/.claude/rules/ auto-loads into every session and every
     subagent. This file lives in reference/ (deployed to ~/.claude/reference/),
     so it loads only when a prompt names it with an explicit `Read` line. -->

# codesight MCP Fallback

Canonical fallback text for `mcp__codesight__query` failures, referenced by the
live coding-team review agents (ct-spec-reviewer, ct-harden-auditor,
ct-simplify-auditor, ct-qa-reviewer, and others that use codesight).

If `mcp__codesight__query` returns a connection error, timeout, or API error:
do NOT retry it. Mark the tool unavailable for this session and fall back to
Grep/Read for the same lookup (symbol search, caller search, call-chain
tracing, dependency search, etc.). Known rationalization: "maybe it's back up
now" — it isn't. One retry is the maximum. Do NOT skip the underlying check
(dependency verification, duplicate detection, data-flow tracing, etc.) just
because codesight is down — perform it with Grep/Read instead.

This mirrors the repo-wide MCP-resilience pattern in `reference/mcp-resilience.md`:
retry once max, then degrade gracefully to built-in tools.
