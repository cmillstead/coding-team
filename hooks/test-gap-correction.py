#!/usr/bin/env python3
"""PostToolUse hook: detect hook files missing corresponding test files.

Strengthens the Correct verb. When a hook .py file is written or edited
but has no corresponding test_*.py file, emits an advisory to prevent
test-coverage-attrition (historically takes 3+ audit cycles to fix).
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from _lib.event import parse_event, get_tool_name, get_file_path
from _lib.output import advisory

# Files that are not hooks and should be skipped
SKIP_NAMES = {"conftest.py", "__init__.py"}


def is_hook_file(file_path: str) -> bool:
    """Check if file_path is a hook .py file inside a hooks/ directory.

    Returns False for files in tests/, _lib/, or non-.py files.
    """
    p = Path(file_path)

    # Must be a .py file
    if p.suffix != ".py":
        return False

    # Must be inside a hooks/ directory
    parts = p.parts
    if "hooks" not in parts:
        return False

    # Get the index of the last 'hooks' directory
    hooks_idx = len(parts) - 1 - list(reversed(parts)).index("hooks")

    # File must be a direct child of hooks/ (not in a subdirectory like tests/ or _lib/)
    if len(parts) != hooks_idx + 2:
        return False

    # Skip known non-hook files
    if p.name in SKIP_NAMES:
        return False

    return True


def derive_test_path(file_path: str) -> Path:
    """Derive the expected test file path for a hook file."""
    p = Path(file_path)
    # Convert hook-name.py -> test_hook_name.py
    hook_name = p.stem.replace("-", "_")
    return p.parent / "tests" / f"test_{hook_name}.py"


def main():
    data = parse_event()
    if not data:
        return

    tool = get_tool_name(data)
    if tool not in ("Write", "Edit"):
        return

    file_path = get_file_path(data)
    if not file_path:
        return

    if not is_hook_file(file_path):
        return

    test_path = derive_test_path(file_path)
    if test_path.exists():
        return

    hook_name = Path(file_path).name
    advisory(
        f"TEST GAP: {hook_name} has no test file. "
        f"Expected: {test_path}. "
        f"Create a test file with at least: tool filtering, skip conditions, and advisory output tests. "
        f"Known rationalization: 'I will add tests in a follow-up' "
        f"— test-coverage-attrition takes 3+ audit cycles to fix. Write tests now."
    )


if __name__ == "__main__":
    main()
