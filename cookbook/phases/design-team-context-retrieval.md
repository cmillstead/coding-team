# Design Team: Context Retrieval

Loaded on demand by `cookbook/phases/design-team.md`. Procedural steps for gathering team memory, episode context, golden principles, and code style before spawning design workers.

## Episode & Context Retrieval

Before spawning workers, retrieve relevant context from prior sessions. Two sources: project-local team memory and vault episodes.

### Project team memory

```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
```

Check if `$REPO_ROOT/docs/team-memory.md` exists using the Read tool:
- **If it exists:** Read it using the Read tool. Pass the full contents to the Team Leader as a "## Team Memory" section in the context. The Team Leader passes relevant subsections to each worker.
- **If it doesn't exist:** Skip. Do NOT create it — the completion phase handles creation.

### Episode retrieval

Use QMD `vector_search` tool (NOT `search`) to find relevant past episodes. Vector search matches by meaning — a query about "adding a REST endpoint" will find episodes about schema drift, auth patterns, or API design even if those episodes never mention "REST."

```
vector_search({
  query: "<1-2 sentence description of what this task is trying to accomplish and what areas of the codebase it touches>",
  collection: "conversations",
  limit: 3,
  minScore: 0.4
})
```

If episodes are found:
- Read the top 1-2 results using the Read tool (skip if minScore threshold filters them all out)
- Extract the "Patterns Discovered" and "What Would Help Next Time" sections
- Pass these to the Team Leader as an "## Episode Context" section:

```markdown
## Episode Context

> Patterns from similar past work. Workers should check whether these apply.

**From <episode title> (YYYY-MM-DD):**
- Pattern: <pattern>
- Watch out for: <what would help next time>
```

If no episodes found or scores are below threshold: skip and note in status: 'Episode retrieval not available — skipped'. Do NOT fabricate episode context.

### Golden principles

Read `~/.claude/golden-principles.md` using the Read tool. Pass the full contents to the Team Leader as a "## Golden Principles" section in the context. Design workers making architecture recommendations MUST check their proposals against these principles.

If the file doesn't exist, skip and note in status: 'Golden principles not available — skipped'

### Code style

Read `~/.claude/code-style.md` using the Read tool. Pass the full contents to the Team Leader as a "## Code Style" section in the context. Design workers making implementation recommendations should be aware of the project's coding conventions.

If the file doesn't exist, skip and note in status: 'Code style not available — skipped'

### Passing context to workers

The Team Leader includes team memory and episode context in each worker's spawn prompt, after the project context and before the specialist focus areas. Workers treat these as advisory — they inform analysis but don't constrain it.
