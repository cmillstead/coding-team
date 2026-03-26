#!/usr/bin/env python3
"""Claude Code PreToolUse hook: block git add of secret/credential files.

You are a credential leak prevention gate. Fires before Bash tool calls
that contain `git add` and checks if any targeted files match secret patterns.

Blocked patterns: .env, *.key, *.pem, credentials.*, *.secret, *.p12, *.pfx
Also warns on `git add -A` / `git add --all` / `git add .` (prefer explicit file listing).

Named rationalization: "It's just a test file" — test credentials are still credentials.
If the file is genuinely safe, use `git add --force <file>` or add it to .gitignore.
"""

import json
import re
import sys
from pathlib import Path

# File patterns that indicate secrets/credentials
SECRET_NAMES = {".env", ".env.local", ".env.production", ".env.staging", ".env.development"}
SECRET_SUFFIXES = {".key", ".pem", ".secret", ".p12", ".pfx", ".jks", ".keystore"}
SECRET_PREFIXES = {"credentials", "secret", "serviceaccount"}

# Broad add patterns that bypass explicit file listing
BROAD_ADD_PATTERNS = [
    re.compile(r'\bgit\s+add\s+(-A|--all)\b'),
    re.compile(r'\bgit\s+add\s+\.\s*$'),
    re.compile(r'\bgit\s+add\s+\.\s*&&'),
]

# Match git add with file arguments
GIT_ADD_PATTERN = re.compile(r'\bgit\s+add\s+(.*)')


def is_secret_file(filepath: str) -> str | None:
    """Check if a filepath matches secret patterns. Returns the reason or None."""
    path = Path(filepath)

    if path.name in SECRET_NAMES:
        return f"secret filename '{path.name}'"

    if path.suffix in SECRET_SUFFIXES:
        return f"secret extension '{path.suffix}'"

    if path.stem.lower() in SECRET_PREFIXES:
        return f"secret prefix '{path.stem}'"

    # credentials.* pattern (e.g., credentials.json, credentials.yaml)
    if path.stem.lower() == "credentials":
        return f"credentials file '{path.name}'"

    return None


def extract_files_from_git_add(command: str) -> list[str]:
    """Extract file arguments from a git add command."""
    match = GIT_ADD_PATTERN.search(command)
    if not match:
        return []

    args_str = match.group(1).strip()
    # Split on spaces, filter out flags (start with -)
    parts = args_str.split()
    files = [p for p in parts if not p.startswith("-") and p != "."]
    return files


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return  # malformed input, skip silently

    tool_name = event.get("tool_name", "")
    if tool_name != "Bash":
        return

    command = event.get("tool_input", {}).get("command", "")
    if not command or "git add" not in command:
        return

    # Check for broad add patterns
    for pattern in BROAD_ADD_PATTERNS:
        if pattern.search(command):
            print(json.dumps({
                "decision": "block",
                "reason": (
                    "BLOCKED: 'git add -A' / 'git add .' adds ALL files including secrets.\n\n"
                    "Use explicit file listing instead: git add file1.py file2.py\n"
                    "This prevents accidentally staging .env, *.key, *.pem, and other credential files.\n\n"
                    "Known rationalization: 'I checked, there are no secrets' — "
                    "explicit listing is the policy regardless. .gitignore may have gaps."
                ),
            }))
            return

    # Extract and check individual files
    files = extract_files_from_git_add(command)
    blocked = []
    for f in files:
        reason = is_secret_file(f)
        if reason:
            blocked.append((f, reason))

    if blocked:
        msg = "BLOCKED: git add targets secret/credential file(s).\n\n"
        for filepath, reason in blocked:
            msg += f"  - '{filepath}': {reason}\n"
        msg += (
            "\nGolden Principle #9: Ask Before High-Impact Changes.\n"
            "If this file is genuinely safe to commit:\n"
            "  1. Add it to .gitignore if it shouldn't be tracked\n"
            "  2. Or remove the secret content first\n\n"
            "Known rationalization: 'It's just a test file' — "
            "test credentials are still credentials."
        )
        print(json.dumps({
            "decision": "block",
            "reason": msg,
        }))


if __name__ == "__main__":
    main()
