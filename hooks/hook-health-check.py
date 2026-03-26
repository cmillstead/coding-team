#!/usr/bin/env python3
"""Claude Code SessionStart hook: verify all Python hooks are healthy.

Runs each Python hook in ~/.claude/hooks/ with empty JSON input and a timeout.
Reports any hooks that crash, have syntax errors, or timeout. A broken hook
silently degrades to no protection — this hook makes that degradation visible.

Does NOT block the session — verification is advisory. A broken hook should
be fixed, not prevent work.

Note: This hook verifies STRUCTURAL health only (syntax errors, import failures,
crashes, timeouts). It does NOT verify behavioral correctness — that is covered
by the pytest suite in hooks/tests/. A hook that passes health check but has a
logic bug will still be caught by the test suite.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

HOOKS_DIR = Path.home() / ".claude" / "hooks"
SETTINGS_PATH = Path.home() / ".claude" / "settings.json"
TIMEOUT_SECONDS = 5


def check_hook(hook_path: Path) -> str | None:
    """Run a hook with empty JSON input and check for crashes.

    Returns an error message string if the hook is unhealthy, None if OK.
    """
    try:
        result = subprocess.run(
            [sys.executable, str(hook_path)],
            input='{}',
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
        # Exit code 0 or 1 are both acceptable (hook may reject empty input)
        # Exit code 2+ or stderr with "Error"/"Traceback" indicates a problem
        if result.returncode > 1:
            stderr_snippet = result.stderr.strip()[:200] if result.stderr else "no stderr"
            return f"exit code {result.returncode}: {stderr_snippet}"
        if result.stderr and ("Traceback" in result.stderr or "SyntaxError" in result.stderr):
            stderr_snippet = result.stderr.strip()[:200]
            return f"stderr: {stderr_snippet}"
        return None
    except subprocess.TimeoutExpired:
        return f"timeout after {TIMEOUT_SECONDS}s"
    except FileNotFoundError:
        return "python3 not found"
    except OSError as e:
        return f"OSError: {e}"


def check_sh_hook(hook_path: Path) -> str | None:
    """Run bash -n on a shell hook to check for syntax errors.

    Returns an error message string if the hook is unhealthy, None if OK.
    """
    try:
        result = subprocess.run(
            ["bash", "-n", str(hook_path)],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            stderr_snippet = result.stderr.strip()[:200] if result.stderr else "syntax error"
            return f"bash syntax error: {stderr_snippet}"
        return None
    except subprocess.TimeoutExpired:
        return f"timeout after {TIMEOUT_SECONDS}s"
    except FileNotFoundError:
        return "bash not found"
    except OSError as e:
        return f"OSError: {e}"


def get_external_hook_paths() -> list[Path]:
    """Extract hook file paths from settings.json that are outside ~/.claude/hooks/.

    Parses all hook entries across SessionStart, PreToolUse, PostToolUse and
    extracts command paths. Returns unique paths that are NOT inside HOOKS_DIR
    (those are already checked by the main loop).
    """
    if not SETTINGS_PATH.is_file():
        return []

    try:
        settings = json.loads(SETTINGS_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return []

    hooks_config = settings.get("hooks", {})
    seen = set()
    external_paths = []

    for event_type in ("SessionStart", "PreToolUse", "PostToolUse"):
        for matcher_block in hooks_config.get(event_type, []):
            for hook_entry in matcher_block.get("hooks", []):
                command = hook_entry.get("command", "")
                if not command:
                    continue
                # Extract the file path from commands like "python3 ~/.config/foo.py"
                # or "bash ~/.claude/hooks/bar.sh"
                parts = command.split()
                if len(parts) < 2:
                    continue
                # The file path is typically the last argument
                file_str = parts[-1]
                # Expand ~ to home directory
                file_path = Path(file_str).expanduser().resolve()
                # Skip paths inside HOOKS_DIR (already checked by main loop)
                try:
                    file_path.relative_to(HOOKS_DIR.resolve())
                    continue  # Inside HOOKS_DIR, skip
                except ValueError:
                    pass  # Outside HOOKS_DIR, include
                if file_path not in seen:
                    seen.add(file_path)
                    external_paths.append(file_path)

    return external_paths


def check_external_hook(hook_path: Path) -> str | None:
    """Check an external hook file for health.

    Returns an error message if unhealthy, None if OK.
    Delegates to check_hook() for .py files and check_sh_hook() for .sh files.
    """
    if not hook_path.is_file():
        return "file not found"

    suffix = hook_path.suffix.lower()
    if suffix == ".py":
        return check_hook(hook_path)
    elif suffix == ".sh":
        return check_sh_hook(hook_path)
    else:
        return None  # Unknown type, skip silently


def check_mcp_health() -> list[str]:
    """Probe configured MCP servers for availability.

    Checks whether codesight-mcp and qmd binaries are reachable via PATH
    or common install locations. Returns a list of warning strings for
    any servers that cannot be found.
    """
    issues = []

    # Check codesight-mcp binary availability
    if not shutil.which("codesight-mcp"):
        common_paths = [
            Path.home() / ".local" / "bin" / "codesight-mcp",
            Path("/usr/local/bin/codesight-mcp"),
        ]
        if not any(p.exists() for p in common_paths):
            issues.append("codesight-mcp binary not found in PATH or common locations")

    # Check qmd binary availability
    if not shutil.which("qmd"):
        common_paths = [
            Path("/opt/homebrew/bin/qmd"),
            Path("/usr/local/bin/qmd"),
        ]
        if not any(p.exists() for p in common_paths):
            issues.append("qmd binary not found in PATH or common locations")

    return issues


def main():
    if not HOOKS_DIR.is_dir():
        return

    unhealthy = []
    for hook_path in sorted(HOOKS_DIR.glob("*.py")):
        # Skip self to avoid recursion
        if hook_path.name == "hook-health-check.py":
            continue
        error = check_hook(hook_path)
        if error:
            unhealthy.append(f"  - {hook_path.name}: {error}")

    for hook_path in sorted(HOOKS_DIR.glob("*.sh")):
        error = check_sh_hook(hook_path)
        if error:
            unhealthy.append(f"  - {hook_path.name}: {error}")

    # Check external hooks registered in settings.json
    for ext_path in get_external_hook_paths():
        error = check_external_hook(ext_path)
        if error:
            unhealthy.append(f"  - [external] {ext_path}: {error}")

    # Check MCP server availability (advisory warnings, not blockers)
    mcp_issues = check_mcp_health()

    if not unhealthy and not mcp_issues:
        return  # All healthy — silent success

    parts = []
    if unhealthy:
        parts.append(
            f"Hook health check: {len(unhealthy)} unhealthy hook(s) detected.\n"
            "These hooks may silently fail to protect you:\n"
            + "\n".join(unhealthy)
            + "\n\nFix or remove broken hooks to restore protection."
        )
    if mcp_issues:
        parts.append(
            f"MCP health check: {len(mcp_issues)} server(s) unavailable.\n"
            "Agents will waste tool calls discovering this at first use:\n"
            + "\n".join(f"  - {issue}" for issue in mcp_issues)
        )

    msg = "\n\n".join(parts)
    print(json.dumps({"decision": "allow", "reason": msg}))


if __name__ == "__main__":
    main()
