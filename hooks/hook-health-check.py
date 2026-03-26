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
import subprocess
import sys
from pathlib import Path

HOOKS_DIR = Path.home() / ".claude" / "hooks"
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

    if not unhealthy:
        return  # All hooks healthy — silent success

    msg = (
        f"Hook health check: {len(unhealthy)} unhealthy hook(s) detected.\n"
        "These hooks may silently fail to protect you:\n"
        + "\n".join(unhealthy)
        + "\n\nFix or remove broken hooks to restore protection."
    )
    print(json.dumps({"decision": "allow", "reason": msg}))


if __name__ == "__main__":
    main()
