#!/usr/bin/env python3
"""Claude Code PostToolUse hook: remind to commit agent/hook files to team repo.

Fires on Write|Edit|Bash. If the target file is under ~/.claude/hooks/ or
~/.claude/agents/, reminds to also commit the file to the coding-team repo.
Bash tool detection catches `cp` commands targeting those directories.
"""
import filecmp
import json
import re
import sys
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude"
REPO_ROOT = CLAUDE_DIR / "skills" / "coding-team"

TRACKED_DIRS = {
    CLAUDE_DIR / "hooks": REPO_ROOT / "hooks",
    CLAUDE_DIR / "agents": REPO_ROOT / "agents",
}

# Pattern: cp <src> <dst> where dst contains .claude/hooks/ or .claude/agents/
BASH_CP_PATTERN = re.compile(
    r'cp\s+.+?\s+.*(/\.claude/(hooks|agents)/|~/.claude/(hooks|agents)/)'
)


def _emit_reminder(msg: str) -> None:
    """Print a structured allow decision with a reminder message."""
    print(json.dumps({"decision": "allow", "reason": msg}))


def _check_path(target: Path) -> None:
    """Check if target is under a tracked dir and emit reminder if needed."""
    for deploy_dir, repo_dir in TRACKED_DIRS.items():
        deploy_resolved = deploy_dir.resolve()
        if str(target).startswith(str(deploy_resolved)):
            try:
                relative = target.relative_to(deploy_resolved)
            except ValueError:
                continue
            repo_copy = repo_dir / relative

            if not repo_copy.exists():
                _emit_reminder(
                    f"New file at {target} — no repo copy found at {repo_copy}.\n"
                    f"Remember to copy this file to the team repo and commit it:\n"
                    f"  cp {target} {repo_copy}"
                )
                return
            else:
                try:
                    if not filecmp.cmp(str(target), str(repo_copy), shallow=False):
                        _emit_reminder(
                            f"Deployed file {target.name} differs from repo copy.\n"
                            f"Sync: cp {target} {repo_copy}"
                        )
                        return
                except OSError:
                    pass


def _handle_write_edit(tool_input: dict) -> None:
    """Handle Write or Edit tool invocations."""
    file_path = tool_input.get("file_path", "")
    if not file_path:
        return
    target = Path(file_path).resolve()
    _check_path(target)


def _handle_bash(tool_input: dict) -> None:
    """Handle Bash tool invocations — detect cp to tracked dirs."""
    command = tool_input.get("command", "")
    if BASH_CP_PATTERN.search(command):
        _emit_reminder(
            "Detected cp to ~/.claude/hooks/ or ~/.claude/agents/.\n"
            "Remember to commit the source file to the coding-team repo too."
        )


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return

    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input", {})

    if tool_name in ("Write", "Edit"):
        _handle_write_edit(tool_input)
    elif tool_name == "Bash":
        _handle_bash(tool_input)


if __name__ == "__main__":
    main()
