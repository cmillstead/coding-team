#!/usr/bin/env python3
"""PostToolUse hook: detect deployed-but-unwired hooks (config drift).

Strengthens the Correct verb. When a hook file is written to ~/.claude/hooks/
but is not registered in settings.json, emits an advisory with the exact
registration JSON needed. Prevents dark features from hook deployment.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from _lib.event import parse_event, get_tool_name, get_file_path
from _lib.output import advisory

HOOKS_DIRS = [
    Path.home() / ".claude" / "hooks",
    Path(__file__).parent,  # repo hooks/ dir
]

SETTINGS_PATH = Path.home() / ".claude" / "settings.json"

HOOK_EXTENSIONS = {".py", ".sh"}


def is_hook_file(file_path: str) -> bool:
    """Check if the file is inside a hooks directory and has a hook extension."""
    if not file_path:
        return False
    p = Path(file_path).resolve()
    if p.suffix not in HOOK_EXTENSIONS:
        return False
    # Skip test files and library files
    if "/tests/" in str(p) or "/_lib/" in str(p):
        return False
    for hooks_dir in HOOKS_DIRS:
        try:
            resolved = hooks_dir.resolve()
            if str(p).startswith(str(resolved) + "/") or p == resolved:
                return True
        except OSError:
            continue
    return False


def extract_hook_filename(file_path: str) -> str:
    """Extract just the filename from a hook path."""
    return Path(file_path).name


def is_registered(filename: str, settings: dict) -> bool:
    """Check if a hook filename appears in any settings.json hook command."""
    hooks = settings.get("hooks", {})
    for _event_name, matchers in hooks.items():
        if not isinstance(matchers, list):
            continue
        for matcher_group in matchers:
            if not isinstance(matcher_group, dict):
                continue
            for hook in matcher_group.get("hooks", []):
                if not isinstance(hook, dict):
                    continue
                command = hook.get("command", "")
                if filename in command:
                    return True
    return False


def suggest_registration(filename: str, file_path: str) -> str:
    """Generate suggested registration JSON."""
    # Determine the runner based on extension
    ext = Path(filename).suffix
    runner = "python3" if ext == ".py" else "bash"
    # Use ~/.claude/hooks/ path for the command
    command = f"{runner} ~/.claude/hooks/{filename}"

    return (
        f"CONFIG DRIFT: {filename} was written but is NOT registered in "
        f"~/.claude/settings.json. This hook will never fire until registered.\n"
        f"Add to the appropriate event in settings.json hooks section:\n"
        f'{{"type": "command", "command": "{command}"}}'
    )


def main():
    data = parse_event()
    if not data:
        return

    tool = get_tool_name(data)
    if tool not in ("Write", "Edit"):
        return

    file_path = get_file_path(data)
    if not is_hook_file(file_path):
        return

    filename = extract_hook_filename(file_path)

    # Graceful degradation: if settings.json can't be read, allow silently
    try:
        settings = json.loads(SETTINGS_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return

    if not is_registered(filename, settings):
        advisory(suggest_registration(filename, file_path))


if __name__ == "__main__":
    main()
