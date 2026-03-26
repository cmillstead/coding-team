#!/usr/bin/env python3
"""Claude Code PreToolUse hook: advisory warnings for high-impact changes.

You are a high-impact change advisor. Fires before Edit/Write/Bash tool calls
that match high-impact patterns: dependency additions, migration creation,
and multi-module changes.

This hook NEVER blocks — it only advises. All decisions are "allow" with a reason.
The goal is awareness, not prevention.

Named rationalization: "It's a minor change" — minor changes to dependencies,
migrations, or multi-module scope still need awareness.
"""

import json
import re
import sys
from pathlib import Path

# Dependency installation commands
DEPENDENCY_PATTERNS = [
    re.compile(r'\bnpm\s+(install|add|i)\s+(?!-)[^\s]'),
    re.compile(r'\byarn\s+add\s+'),
    re.compile(r'\bpip\s+install\s+(?!-r\b|-e\b)'),
    re.compile(r'\bcargo\s+add\s+'),
    re.compile(r'\bpoetry\s+add\s+'),
    re.compile(r'\bpnpm\s+(add|install)\s+(?!-)[^\s]'),
]

# Migration creation commands
MIGRATION_CMD_PATTERNS = [
    re.compile(r'\bmakemigrations\b'),
    re.compile(r'\balembic\s+revision\b'),
    re.compile(r'\bmigrate\s+generate\b'),
    re.compile(r'\bprisma\s+migrate\s+dev\b'),
    re.compile(r'\bknex\s+migrate:make\b'),
    re.compile(r'\brails\s+g(enerate)?\s+migration\b'),
]

# Dependency manifest files
DEPENDENCY_FILES = {
    "package.json", "package-lock.json",
    "pyproject.toml", "requirements.txt", "Pipfile",
    "Cargo.toml", "Cargo.lock",
    "go.mod", "go.sum",
    "Gemfile", "Gemfile.lock",
    "composer.json", "composer.lock",
}


def check_bash_command(command: str) -> str | None:
    """Check a Bash command for high-impact patterns. Returns advisory or None."""
    for pattern in DEPENDENCY_PATTERNS:
        if pattern.search(command):
            return (
                "Adding a new dependency. Golden Principle #9: Ask Before High-Impact Changes.\n"
                "Verify this dependency is approved per project guidelines."
            )

    for pattern in MIGRATION_CMD_PATTERNS:
        if pattern.search(command):
            return (
                "Creating a new migration. Golden Principle #9: Ask Before High-Impact Changes.\n"
                "Verify schema change is approved and includes rollback logic."
            )

    return None


def check_file_edit(file_path: str) -> str | None:
    """Check if a file edit targets a high-impact file. Returns advisory or None."""
    path = Path(file_path)

    # Dependency manifest changes
    if path.name in DEPENDENCY_FILES:
        return (
            f"Editing dependency manifest '{path.name}'. "
            "Golden Principle #9: Ask Before High-Impact Changes.\n"
            "Verify dependency changes are approved."
        )

    return None


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return  # malformed input, skip silently

    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input", {})
    advisory = None

    if tool_name == "Bash":
        command = tool_input.get("command", "")
        if command:
            advisory = check_bash_command(command)

    elif tool_name in ("Edit", "Write"):
        file_path = tool_input.get("file_path", "")
        if file_path:
            advisory = check_file_edit(file_path)

    if advisory:
        print(json.dumps({
            "decision": "allow",
            "reason": advisory,
        }))


if __name__ == "__main__":
    main()
