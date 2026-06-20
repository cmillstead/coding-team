#!/usr/bin/env python3
"""UserPromptSubmit hook dispatcher (D195).

Runs all 8 UserPromptSubmit hooks in a single Python process via runpy.run_path,
preserving registration order and byte-identical output vs 8 separate subprocesses.

Per-hook loop contract (Codex-revised spec, §"Per-hook loop contract"):
  - Read real stdin once into `payload`.
  - For each hook: set sys.stdin = io.StringIO(payload), capture stdout via
    contextlib.redirect_stdout, set sys.argv = [hook_path], run via
    runpy.run_path(hook_path, run_name="__main__").
  - Handle SystemExit (0/None = success, non-zero = soft-fail) and normal return.
  - Restore sys.stdin, sys.stdout, sys.argv after each hook.
  - No dispatcher-level timeout (each hook owns its own subprocess timeout=5).
  - Errors → stderr only, one line naming hook + exception repr.
  - Output: concatenate each captured stdout chunk, zero post-processing, emit to
    real stdout. No JSON envelope, no decision.
  - Dispatcher ALWAYS exits 0.

Escape hatches:
  CT_PROMPT_DISPATCHER_DISABLE=1   → exit 0 immediately, no output.
  CT_PROMPT_DISPATCHER_SKIP="a,b"  → skip hooks whose basename matches any name.
  --only <basename>                 → run only that one hook through dispatcher path.
"""

import contextlib
import io
import os
import runpy
import sys
from pathlib import Path

# Registration order — MUST be preserved (spec §"The 8 hooks").
HOOK_PATHS: list[str] = [
    "/Users/cevin/src/engram/.base/hooks/active-hook.py",
    "/Users/cevin/src/engram/.base/hooks/backlog-hook.py",
    "/Users/cevin/src/engram/.base/hooks/base-pulse-check.py",
    "/Users/cevin/src/engram/.base/hooks/psmm-injector.py",
    "/Users/cevin/src/engram/.base/hooks/base-operator.py",
    "/Users/cevin/.claude/hooks/session-capture-check.py",
    "/Users/cevin/.claude/hooks/proactive-recall.py",
    "/Users/cevin/.claude/hooks/mid-session-recall.py",
]


def _resolve_hooks(only_name: str | None, skip_names: set[str]) -> list[str]:
    """Return the ordered list of hook paths to run, applying escape hatches."""
    if only_name:
        matched = [p for p in HOOK_PATHS if Path(p).name == only_name]
        if not matched:
            print(
                f"prompt-dispatcher: --only '{only_name}' matched no hook basename",
                file=sys.stderr,
            )
        return matched
    return [p for p in HOOK_PATHS if Path(p).name not in skip_names]


def _run_hook(hook_path: str, payload: str, real_stdout: io.TextIOBase) -> None:
    """Run one hook in-process, capturing its stdout.

    Restores sys.stdin, sys.stdout, sys.argv regardless of outcome.
    Errors are written to real stderr (never stdout). Dispatcher never re-raises.
    """
    saved_stdin = sys.stdin
    saved_stdout = sys.stdout
    saved_argv = sys.argv[:]

    capture_buf = io.StringIO()

    try:
        sys.stdin = io.StringIO(payload)
        sys.argv = [hook_path]
        with contextlib.redirect_stdout(capture_buf):
            try:
                runpy.run_path(hook_path, run_name="__main__")
            except SystemExit as exc:
                code = exc.code
                if code is not None and code != 0:
                    print(
                        f"prompt-dispatcher: soft-fail {Path(hook_path).name}"
                        f" exited {code!r}",
                        file=sys.stderr,
                    )
                # code 0 or None → success (normal hook exit)
    except BaseException as exc:  # noqa: BLE001 — catch-all by design; errors go to stderr
        print(
            f"prompt-dispatcher: error in {Path(hook_path).name}: {exc!r}",
            file=sys.stderr,
        )
    finally:
        sys.stdin = saved_stdin
        sys.stdout = saved_stdout
        sys.argv = saved_argv

    # Emit captured output to real stdout — zero post-processing.
    chunk = capture_buf.getvalue()
    if chunk:
        real_stdout.write(chunk)


def main() -> None:
    # Escape hatch: disable entire dispatcher.
    if os.environ.get("CT_PROMPT_DISPATCHER_DISABLE") == "1":
        sys.exit(0)

    # Escape hatch: skip specific hook basenames.
    skip_env = os.environ.get("CT_PROMPT_DISPATCHER_SKIP", "")
    skip_names: set[str] = {name.strip() for name in skip_env.split(",") if name.strip()}

    # Escape hatch: --only <basename> runs exactly one hook.
    only_name: str | None = None
    args = sys.argv[1:]
    if len(args) >= 2 and args[0] == "--only":
        only_name = args[1]

    hooks_to_run = _resolve_hooks(only_name, skip_names)

    # Read real stdin once — each hook gets a fresh io.StringIO copy.
    try:
        payload = sys.stdin.read()
    except OSError:
        payload = ""

    real_stdout = sys.stdout

    for hook_path in hooks_to_run:
        _run_hook(hook_path, payload, real_stdout)

    # Dispatcher always exits 0 — context-injection hooks must never block a prompt.
    sys.exit(0)


if __name__ == "__main__":
    main()
