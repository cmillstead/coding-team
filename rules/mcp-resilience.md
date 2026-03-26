# MCP Resilience

When an MCP tool call fails (timeout, connection error, server unavailable):

1. Retry exactly once with the same parameters
2. If the retry fails, mark that MCP tool as unavailable for the remainder of the session
3. Degrade gracefully to built-in tools: Glob, Grep, Read, Bash
4. Do NOT retry a failed MCP tool more than once per session

Known rationalizations:
- "Maybe it's back up now" — it is not. One retry is the maximum.
- "I need this specific MCP tool" — the built-in tools can accomplish the same task, just less efficiently.
- "Let me try a different query" — the issue is the MCP server, not the query. Changing parameters does not fix a down server.

This rule applies to ALL agents, not just specific workers.
