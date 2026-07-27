# Engram Knowledge Graph

Use engram for structured knowledge — nodes, edges, relationships, dimensions. Prefer CLI with `--json` over MCP tools when the dev server is running (`npm run dev`).

## Core commands

```bash
engram search "query" --json                    # Full-text + vector search
engram search-debug "query" --json              # Search with scoring/ranking debug info
engram query-nodes --filter '{"type":"note"}' --json  # Structured node query
engram get-node <id> --json                     # Fetch node by ID
engram add-node "title" --description "..." --json
engram update-node <id> --description "..." --json
engram delete-node <id> --json
engram get-context --json                       # Context for current session
engram since-last-session --json                # What changed since last session
engram capture-session --json                   # Capture current session state
engram export --json                            # Export full graph
engram import-bulk <file> --json                # Bulk import nodes/edges
```

## Edges

```bash
engram create-edge --from <id> --to <id> --type "related_to" --json
engram query-edges --node <id> --json
engram delete-edge <id> --json
```

## Recall (key-value memory)

```bash
engram recall-get <key> --json
engram recall-set <key> <value> --json
engram list-recall --json
engram delete-recall <key> --json
```

## Dimensions & exploration

```bash
engram query-dimensions --json
engram create-dimension <name> --json            # Create a new dimension
engram sql "SELECT count(*) FROM nodes" --json   # Raw SQLite query
```
