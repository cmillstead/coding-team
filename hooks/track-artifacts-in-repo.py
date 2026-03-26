#!/usr/bin/env python3
"""Claude Code PostToolUse hook: remind to commit agent/hook files to team repo.

Fires on Write|Edit. If the target file is under ~/.claude/hooks/ or
~/.claude/agents/, reminds to also commit the file to the coding-team repo.
"""
import json
import sys
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude"
REPO_ROOT = CLAUDE_DIR / "skills" / "coding-team"

TRACKED_DIRS = {
    CLAUDE_DIR / "hooks": REPO_ROOT / "hooks",
    CLAUDE_DIR / "agents": REPO_ROOT / "agents",
}


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return

    tool_name = event.get("tool_name", "")
    if tool_name not in ("Write", "Edit"):
        return

    tool_input = event.get("tool_input", {})
    file_path = tool_input.get("file_path", "")
    if not file_path:
        return

    target = Path(file_path).resolve()

    for deploy_dir, repo_dir in TRACKED_DIRS.items():
        deploy_resolved = deploy_dir.resolve()
        if str(target).startswith(str(deploy_resolved)):
            relative = target.relative_to(deploy_resolved)
            repo_copy = repo_dir / relative

            if not repo_copy.exists():
                msg = (
                    f"New file at {target} — no repo copy found at {repo_copy}.\n"
                    f"Remember to copy this file to the team repo and commit it:\n"
                    f"  cp {target} {repo_copy}"
                )
                print(json.dumps({"decision": "allow", "reason": msg}))
                return
            else:
                try:
                    if target.stat().st_size != repo_copy.stat().st_size:
                        msg = (
                            f"Deployed file {target.name} differs from repo copy.\n"
                            f"Sync: cp {target} {repo_copy}"
                        )
                        print(json.dumps({"decision": "allow", "reason": msg}))
                        return
                except OSError:
                    pass


if __name__ == "__main__":
    main()
