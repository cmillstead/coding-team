# Design Team: Context Retrieval

Loaded on demand by `phases/design-team.md`. Procedural steps for gathering team memory, episode context, golden principles, and code style before spawning design workers.

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

Use the engram CLI to find relevant past episodes — `engram search "<query>" --json` (full-text + vector matches by meaning — a query about "adding a REST endpoint" will find episodes about schema drift, auth patterns, or API design even if those episodes never mention "REST.").

```
engram search "<1-2 sentence description of what this task is trying to accomplish and what areas of the codebase it touches>" --json
```

Take the top ~3 results from the JSON.

If episodes are found:
- Read the top 1-2 results (skip if scores are too low). Search results carry title/description; fetch full content via `engram get-node <id> --json` if needed.
- Extract the "Patterns Discovered" and "What Would Help Next Time" sections
- Pass these to the Team Leader as an "## Episode Context" section:

```markdown
## Episode Context

> Patterns from similar past work. Workers should check whether these apply.

**From <episode title> (YYYY-MM-DD):**
- Pattern: <pattern>
- Watch out for: <what would help next time>
```

If no episodes found or results are below useful quality: skip and note in status: 'Episode retrieval not available — skipped'. Do NOT fabricate episode context.

### Golden principles

**Tier gate:** If the planned tier is Trivial AND the task contains no architectural decision, SKIP the golden-principles read and pass-through. Trivial tasks with no arch decision do not need architecture-governance review — loading and passing the full file adds context cost with no signal benefit.

If the planned tier is Small/Medium/Large, OR the task contains an architectural decision at any tier: Read `~/.claude/golden-principles.md` using the Read tool. Pass the full contents to the Team Leader as a "## Golden Principles" section in the context. Design workers making architecture recommendations MUST check their proposals against these principles.

If the file doesn't exist, skip and note in status: 'Golden principles not available — skipped'

### Code style

Read `~/.claude/code-style.md` using the Read tool. Pass the full contents to the Team Leader as a "## Code Style" section in the context. Design workers making implementation recommendations should be aware of the project's coding conventions.

If the file doesn't exist, skip and note in status: 'Code style not available — skipped'

### Passing context to workers

The Team Leader includes team memory and episode context in each worker's spawn prompt, after the project context and before the specialist focus areas. Workers treat these as advisory — they inform analysis but don't constrain it.
