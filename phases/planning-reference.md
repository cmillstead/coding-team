# Planning Reference

On-demand detail extracted from `phases/planning.md`.

## Step 0.75: Code Intelligence (before writing tasks)

Use these tools to understand the codebase structure before decomposing tasks:

| Tool | When to use |
|---|---|
| `mcp__codesight__query` (operation `get-file-tree`) | Understand repo layout, identify where new code should live |
| `mcp__codesight__query` (operation `get-repo-outline`) | See key symbols across the codebase before planning changes |
| `mcp__codesight__query` (operation `analyze-complexity`) | Check files the plan will modify — split files with cyclomatic complexity above 15 |
| `mcp__codesight__query` (operation `search-symbols`) | Find existing utilities that sub-tasks could reuse instead of rebuilding |
| `mcp__codesight__query` (operation `get-dependencies`) | Check for circular dependency risks in files the plan will modify |
| `mcp__codesight__query` (operation `get-type-hierarchy`) | Understand full class hierarchy before planning changes to base classes |
| `mcp__codesight__query` (operation `get-key-symbols`) | Identify architecturally significant symbols — focuses planning on high-impact areas |
| `mcp__codesight__query` (operation `get-diagram`) | Generate architecture diagrams — include in the plan for implementers |
| `gh search issues` (or `gh issue list --search`) | Find related issues — prior discussion contains requirements or edge cases not in the spec |
| `gh search prs` (or `gh pr list --search`) | Check if similar work was previously attempted — learn from prior approaches |
| `mcp__context-keep__search_memories` | Find relevant prior architectural decisions — avoid contradicting established patterns |

If a `mcp__codesight__query` call fails, fall back to Grep/Read for that query. If the codesight MCP server is not running, fall back to Glob and Grep tools. Do NOT skip codebase analysis — use whichever tools are available.
