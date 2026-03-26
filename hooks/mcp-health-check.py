#!/usr/bin/env python3
"""PreToolUse hook: best-effort MCP server liveness check with warning."""
import json
import os
import subprocess
import sys
import time


CACHE_DIR = "/tmp"
CACHE_TTL = 60  # seconds


def get_server_name(tool_name: str) -> str:
    """Extract MCP server name from tool_name like mcp__codesight-mcp__search_text."""
    parts = tool_name.split("__")
    if len(parts) >= 2:
        return parts[1]
    return ""


def check_cache(server_name: str) -> bool:
    """Return True if server was recently confirmed healthy."""
    cache_file = os.path.join(CACHE_DIR, f"mcp-health-{server_name}")
    try:
        if os.path.exists(cache_file):
            with open(cache_file) as f:
                ts = float(f.read().strip())
            if time.time() - ts < CACHE_TTL:
                return True
    except (OSError, ValueError):
        pass
    return False


def update_cache(server_name: str):
    """Mark server as recently healthy."""
    cache_file = os.path.join(CACHE_DIR, f"mcp-health-{server_name}")
    try:
        with open(cache_file, "w") as f:
            f.write(str(time.time()))
    except OSError:
        pass


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        print(json.dumps({"decision": "allow"}))
        return

    tool_name = data.get("tool_name", "")
    if not tool_name.startswith("mcp__"):
        print(json.dumps({"decision": "allow"}))
        return

    server_name = get_server_name(tool_name)
    if not server_name:
        print(json.dumps({"decision": "allow"}))
        return

    # Check cache first
    if check_cache(server_name):
        print(json.dumps({"decision": "allow"}))
        return

    # Best-effort pgrep check
    try:
        result = subprocess.run(
            ["pgrep", "-f", server_name],
            capture_output=True, text=True, timeout=3
        )
        if result.returncode == 0:
            # Process found — server is likely running
            update_cache(server_name)
            print(json.dumps({"decision": "allow"}))
            return
        else:
            # No process found — warn but allow
            print(json.dumps({
                "decision": "allow",
                "reason": (
                    f"MCP server '{server_name}' process not found. "
                    f"Fall back to built-in tools (Grep tool, Read tool, Glob tool) for this request. "
                    f"If the server should be running, check ~/.claude.json or .mcp.json for config."
                ),
            }))
            return
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        # Can't check — allow through silently
        print(json.dumps({"decision": "allow"}))
        return


if __name__ == "__main__":
    main()
