#!/bin/bash
# Auto-reindex codesight-mcp when source files are written within ~/src/.
# PostToolUse hooks receive JSON via stdin with tool_input.file_path.

FILE_PATH=$(jq -r '.tool_input.file_path // empty' 2>/dev/null)

# Only trigger for files under ~/src/ (skip obsidian, config, etc.)
if [[ "$FILE_PATH" == /Users/cevin/src/* ]]; then
    # Walk up to find the project root (first dir containing pyproject.toml, package.json, Cargo.toml, go.mod, or .git)
    DIR="$FILE_PATH"
    PROJECT_ROOT=""
    while [[ "$DIR" != "/Users/cevin/src" && "$DIR" != "/" ]]; do
        DIR=$(dirname "$DIR")
        if [[ -f "$DIR/pyproject.toml" || -f "$DIR/package.json" || -f "$DIR/Cargo.toml" || -f "$DIR/go.mod" || -d "$DIR/.git" ]]; then
            PROJECT_ROOT="$DIR"
            break
        fi
    done

    if [[ -n "$PROJECT_ROOT" ]]; then
        # Debounce: skip if reindexed within last 30 seconds
        DEBOUNCE_FILE="/tmp/codesight-reindex-$(echo "$PROJECT_ROOT" | md5 -q)"
        if [[ -f "$DEBOUNCE_FILE" ]]; then
            LAST_RUN=$(cat "$DEBOUNCE_FILE" 2>/dev/null || echo 0)
            NOW=$(date +%s)
            if (( NOW - LAST_RUN < 30 )); then
                exit 0
            fi
        fi
        date +%s > "$DEBOUNCE_FILE"

        (
            IRONMUNCH_ALLOWED_ROOTS=/Users/cevin/src \
            /Users/cevin/src/ironmunch/.venv/bin/codesight-mcp index "$PROJECT_ROOT" --no-ai 2>&1
        ) >> /private/tmp/claude/codesight-reindex.log 2>&1 &
    fi
fi
