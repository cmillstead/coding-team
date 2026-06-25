#!/usr/bin/env python3
"""PostToolUse hook dispatcher.

Consolidates the per-tool PostToolUse entries from settings.json into a single
matcher="" entry that routes internally by tool_name.

Current PostToolUse topology (before consolidation):
  - Bash                   → loop-detection.py, lint-warning-enforcer.py
  - Skill                  → coding-team-lifecycle.py
  - Write|Edit             → codesight-hooks.py (reindex), builder-self-check.py
  - mcp__codesight__query  → codesight-hooks.py (usage logging)

Why subprocess (not runpy):
  - coding-team-lifecycle.py can emit BLOCKING decisions. Subprocessing it preserves
    its stdout verbatim so the block payload reaches Claude Code unchanged.
  - loop-detection.py and lint-warning-enforcer.py use sys.path.insert(__file__-relative)
    that is safest subprocessed.
  - codesight-hooks.py and builder-self-check.py are side-effect-only for PostToolUse;
    subprocessing them provides full isolation.

Output merging contract (multiple-handler case):
  When multiple handlers match one tool_name (currently Bash: loop-detection +
  lint-warning-enforcer; Write|Edit: codesight-hooks + builder-self-check):
    1. Run ALL applicable handlers regardless of individual results.
    2. Classify each handler's stdout:
         "block"    → {"decision":"block","reason":"..."}
         "advisory" → {"decision":"allow","reason":"..."}
         ""         → silent (no stdout or non-JSON)
    3. First BLOCK wins: emit the block reason and exit immediately.
    4. ADVISORIES are merged: emit one combined advisory with all reasons joined by
       double-newline (same result as seeing both advisories separately).
    5. If all handlers are silent: exit 0 (no output).

Escape hatches:
  CT_POSTTOOLUSE_DISPATCHER_DISABLE=1  → exit 0 immediately.
  CT_POSTTOOLUSE_DISPATCHER_SKIP="a,b" → skip handlers whose basename matches a name.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

HOME = Path(os.path.expanduser("~"))
HOOKS = HOME / ".claude" / "hooks"

# Canonical handler paths.
LOOP_DETECTION = str(HOOKS / "loop-detection.py")
LINT_WARNING_ENFORCER = str(HOOKS / "lint-warning-enforcer.py")
CODING_TEAM_LIFECYCLE = str(HOOKS / "coding-team-lifecycle.py")
CODESIGHT_HOOKS = str(HOOKS / "codesight-hooks.py")
BUILDER_SELF_CHECK = str(HOOKS / "builder-self-check.py")


def _skip_names() -> set[str]:
    """Return set of handler basenames to skip (from env var)."""
    env = os.environ.get("CT_POSTTOOLUSE_DISPATCHER_SKIP", "")
    return {n.strip() for n in env.split(",") if n.strip()}


def _is_skipped(path: str, skip: set[str]) -> bool:
    return Path(path).name in skip


def _run_handler(
    cmd: list[str],
    payload: str,
    *,
    timeout: int = 30,
) -> tuple[str, int]:
    """Run cmd with payload on stdin. Return (raw_stdout, returncode).

    Fully isolated: timeout, FileNotFoundError, OSError, and all other
    exceptions yield ("", 0) so the dispatcher continues. Never raises.
    """
    name = Path(cmd[-1]).name
    try:
        result = subprocess.run(
            cmd,
            input=payload,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout, result.returncode
    except subprocess.TimeoutExpired:
        print(
            f"posttooluse-dispatcher: timeout {name} after {timeout}s",
            file=sys.stderr,
        )
        return "", 0
    except (FileNotFoundError, PermissionError, OSError) as exc:
        print(
            f"posttooluse-dispatcher: cannot run {name}: {exc!r}",
            file=sys.stderr,
        )
        return "", 0
    except Exception as exc:  # noqa: BLE001 — catch-all by design; isolation guarantee
        print(
            f"posttooluse-dispatcher: error in {name}: {exc!r}",
            file=sys.stderr,
        )
        return "", 0


def _classify_output(raw_stdout: str) -> tuple[str, str]:
    """Parse handler stdout into (type, content).

    Returns:
        ("block", reason_string)    — handler wants to block
        ("advisory", reason_string) — handler emits advisory
        ("", "")                    — handler is silent or output unrecognized
    """
    text = raw_stdout.strip()
    if not text:
        return "", ""
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return "", ""
    if not isinstance(obj, dict):
        return "", ""
    decision = obj.get("decision", "")
    reason = obj.get("reason", "")
    if decision == "block":
        return "block", str(reason) if reason else ""
    if decision == "allow" and reason:
        return "advisory", str(reason)
    return "", ""


def _run_and_emit(handlers: list[str], payload: str, skip: set[str]) -> None:
    """Run all handlers, merge outputs, emit one unified response.

    Execution order: handlers are run in registration order. All run regardless
    of each other's output (per-check isolation). Blocks take priority over
    advisories. Multiple advisories are merged into one.
    """
    blocks: list[str] = []
    advisories: list[str] = []

    for script in handlers:
        if _is_skipped(script, skip):
            continue
        stdout, _rc = _run_handler([sys.executable, script], payload)
        kind, content = _classify_output(stdout)
        if kind == "block":
            blocks.append(content)
        elif kind == "advisory":
            advisories.append(content)

    if blocks:
        print(json.dumps({"decision": "block", "reason": "\n\n".join(blocks)}))
        return

    if advisories:
        print(json.dumps({"decision": "allow", "reason": "\n\n".join(advisories)}))


def main() -> None:
    if os.environ.get("CT_POSTTOOLUSE_DISPATCHER_DISABLE") == "1":
        sys.exit(0)

    skip = _skip_names()

    try:
        payload = sys.stdin.read()
    except OSError:
        payload = ""

    try:
        event = json.loads(payload) if payload else {}
    except (json.JSONDecodeError, ValueError):
        event = {}

    tool_name = event.get("tool_name", "")

    if tool_name == "Bash":
        _run_and_emit([LOOP_DETECTION, LINT_WARNING_ENFORCER], payload, skip)

    elif tool_name == "Skill":
        _run_and_emit([CODING_TEAM_LIFECYCLE], payload, skip)

    elif tool_name in ("Write", "Edit"):
        _run_and_emit([CODESIGHT_HOOKS, BUILDER_SELF_CHECK], payload, skip)

    elif tool_name == "mcp__codesight__query":
        _run_and_emit([CODESIGHT_HOOKS], payload, skip)

    # For all other tool names: no handlers registered — exit 0 silently.


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise  # propagate explicit sys.exit() calls
    except Exception as exc:  # noqa: BLE001 — dispatcher crash must never block a session
        import traceback

        print(
            f"posttooluse-dispatcher: CRASH: {exc!r}\n{traceback.format_exc()}",
            file=sys.stderr,
        )
        sys.exit(0)
