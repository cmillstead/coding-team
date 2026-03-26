#!/usr/bin/env python3
"""Claude Code PreToolUse hook: block edits to deployed migration files.

You are a migration integrity guardian. Fires before Edit/Write tool calls
targeting files in known migration directories. Deployed migrations are
immutable — create a new migration instead of modifying an existing one.

Migration directories detected:
- migrations/
- alembic/versions/
- db/migrate/
- prisma/migrations/

Named rationalization: "It's just a comment/docstring change" — any edit to
deployed migrations risks inconsistency between what ran in production and
what's in the repo. Create a new migration instead.
"""

import json
import re
import sys
from pathlib import Path

# Directory names that indicate migration locations
MIGRATION_DIR_NAMES = {"migrations", "versions", "migrate"}

# Parent directory patterns for migration paths
# Using Path.parts for structural matching (Case 35)
MIGRATION_PATH_PATTERNS = [
    ("migrations",),
    ("alembic", "versions"),
    ("db", "migrate"),
    ("prisma", "migrations"),
]

# Migration file name pattern: starts with digits or timestamp
MIGRATION_FILE_PATTERN = re.compile(r'^\d+[_\-]')


def is_migration_file(filepath: str) -> bool:
    """Check if a file path points to a migration file using structural path matching.

    Uses pathlib.Path.parts for reliable matching (Case 35 — no string operations).
    """
    path = Path(filepath)
    parts = path.parts

    # Check if any parent directory sequence matches migration patterns
    for pattern in MIGRATION_PATH_PATTERNS:
        pattern_len = len(pattern)
        for i in range(len(parts) - pattern_len):
            if parts[i:i + pattern_len] == pattern:
                return True

    # Check if the filename matches migration naming conventions
    # AND is inside a directory that could be migrations
    if MIGRATION_FILE_PATTERN.match(path.name):
        for part in parts[:-1]:  # Check parent directories
            if part.lower() in MIGRATION_DIR_NAMES:
                return True

    return False


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return  # malformed input, skip silently

    tool_name = event.get("tool_name", "")
    if tool_name not in ("Edit", "Write"):
        return

    file_path = event.get("tool_input", {}).get("file_path", "")
    if not file_path:
        return

    # Only block Edit (modifying existing migrations), not Write (creating new ones)
    # New migration creation via Write is allowed
    if tool_name == "Write":
        # Check if the file already exists — Write to existing migration = block
        if not Path(file_path).exists():
            return  # New file creation is allowed

    if is_migration_file(file_path):
        path = Path(file_path)
        print(json.dumps({
            "decision": "block",
            "reason": (
                f"BLOCKED: editing deployed migration file '{path.name}'.\n\n"
                f"Deployed migrations are immutable. Create a new migration instead.\n"
                f"See rules/migration-files.md for migration file rules.\n\n"
                f"Golden Principle #9: Ask Before High-Impact Changes.\n"
                f"Modifying a deployed migration can cause:\n"
                f"  - Schema drift between environments\n"
                f"  - Failed rollbacks\n"
                f"  - Data loss\n\n"
                f"Known rationalization: 'It's just a comment/docstring change' — "
                f"any edit to deployed migrations risks inconsistency."
            ),
        }))


if __name__ == "__main__":
    main()
