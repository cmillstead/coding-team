#!/bin/bash
# Auto-run qmd update + embed when files are written to the obsidian vault.
# PostToolUse hooks receive JSON via stdin with tool_input.file_path.

FILE_PATH=$(jq -r '.tool_input.file_path // empty' 2>/dev/null)

if [[ "$FILE_PATH" == *"/obsidian-vault/"* ]]; then
    (
        /opt/homebrew/bin/qmd update --collection obsidian 2>&1
        /opt/homebrew/bin/qmd embed --collection obsidian 2>&1
    ) >> /private/tmp/claude/qmd-auto-embed.log 2>&1 &
fi
