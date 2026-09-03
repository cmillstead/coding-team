#!/usr/bin/env python3
"""PreToolUse hook dispatcher.

Consolidates the per-tool PreToolUse entries (Agent/codesight, Edit|Write/write-guard,
Bash/git-safety-guard, Bash/rtk) from settings.json into a single matcher="" entry
that routes internally by tool_name.

Why subprocess (not runpy like prompt-dispatcher):
  - write-guard and git-safety-guard are BLOCKING guards. Their exact stdout and exit
    code must reach Claude Code verbatim. Running them as subprocesses is the only way
    to guarantee that their block decision (stdout JSON + exit code) is passed through
    without any in-process interference.
  - rtk hook claude is an external binary and must be subprocessed.
  - codesight-hooks.py uses sys.path.insert(__file__-relative) that is safest as a
    subprocess.

Blocking contract (CRITICAL):
  Handlers can signal a BLOCK via two mechanisms:
    (a) stdout JSON {"decision":"block","reason":"..."} + exit code 0
    (b) stderr message + exit code 2

  For both mechanisms, this dispatcher captures the subprocess output verbatim and
  forwards it to real stdout/stderr before exiting with the same exit code.
  No rewriting or re-serialization occurs — the output is byte-identical to running
  the handler directly.

Routing:
  - Agent     → paul-apply-agent-guard.py (Path B fence, blocking, first), then codesight-hooks.py (prompt injection)
  - Read       → engram-pretool-inject.py (non-blocking injector — the ONLY handler
                  in this branch; emits a PreToolUse additionalContext envelope or
                  nothing, never a block)
  - Edit|Write → clean-tree-gate.py (blocking — fires only on the plan
                  in-progress→complete transition, else silent; runs FIRST so a
                  write-guard ALLOW advisory can't pass through ahead of it),
                  then write-guard.py (blocking guard — verbatim passthrough),
                  then engram-pretool-inject.py (non-blocking injector — runs LAST,
                  only if both guards above stayed silent)
  - Bash       → git-safety-guard.py (blocking guard — verbatim passthrough), then
                  rtk hook claude (only if git-safety-guard produced no output)

First-response-wins contract:
  The first handler that produces output (stdout or non-zero exit code) sets the hook
  response. Subsequent handlers for the same tool call are skipped once any handler
  has responded. This mirrors CC's per-hook-entry contract: the first matching entry
  that responds owns the decision.

Escape hatches:
  CT_PRETOOLUSE_DISPATCHER_DISABLE=1  → exit 0 immediately, no output.
  CT_PRETOOLUSE_DISPATCHER_SKIP="a,b" → skip handlers whose basename matches a name.
  CT_ENGRAM_INJECT_PATH=/path        → override the engram injector path (test-only; point
                                        it at a fake injector to prove a crash is swallowed).
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HOME = Path(os.path.expanduser("~"))
HOOKS = HOME / ".claude" / "hooks"

# Canonical handler paths (via symlinks under ~/.claude/hooks/).
WRITE_GUARD = str(HOOKS / "write-guard.py")
GIT_SAFETY_GUARD = str(HOOKS / "git-safety-guard.py")
CODESIGHT_HOOKS = str(HOOKS / "codesight-hooks.py")
PAUL_AGENT_GUARD = str(HOOKS / "paul-apply-agent-guard.py")

# Referenced from the RESOLVED SOURCE dir, not the ~/.claude/hooks symlink dir,
# so the guard is LIVE the moment it is written in this working tree — no separate
# ~/.claude symlink/activation step gates enforcement. `Path(__file__).resolve()`
# follows the dispatcher's own ~/.claude/hooks symlink back to
# ~/.claude/skills/coding-team/hooks/ in production, and is idempotent when the
# dispatcher is run directly from source (tests). The other handlers predate this
# and address their already-deployed ~/.claude/hooks symlinks via HOOKS; only this
# new guard uses the source-dir reference (documented one-off, see plan rationale).
_SRC_HOOKS = Path(__file__).resolve().parent
CLEAN_TREE_GATE = str(_SRC_HOOKS / "clean-tree-gate.py")

# Engram delivery injector (NON-blocking context provider, TRK-209). Source-dir
# reference (live on write, same as CLEAN_TREE_GATE). Env-overridable (mirrors the
# CT_PRETOOLUSE_DISPATCHER_* escape-hatch convention) so a test can point it at a
# fake crashing injector to prove a nonzero injector exit is swallowed.
ENGRAM_INJECT = os.environ.get("CT_ENGRAM_INJECT_PATH", str(_SRC_HOOKS / "engram-pretool-inject.py"))


def _skip_names() -> set[str]:
    """Return set of handler basenames to skip (from env var)."""
    env = os.environ.get("CT_PRETOOLUSE_DISPATCHER_SKIP", "")
    return {n.strip() for n in env.split(",") if n.strip()}


def _is_skipped(path: str, skip: set[str]) -> bool:
    return Path(path).name in skip


def _run_handler(
    cmd: list[str],
    payload: str,
    *,
    timeout: int = 30,
) -> tuple[str, str, int]:
    """Run cmd with payload on stdin. Return (raw_stdout, raw_stderr, returncode).

    Fully isolated: timeout, FileNotFoundError, OSError, and all other
    exceptions yield ("", "", 0) so the dispatcher continues. Never raises.
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
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        print(
            f"pretooluse-dispatcher: timeout {name} after {timeout}s",
            file=sys.stderr,
        )
        return "", "", 0
    except (FileNotFoundError, PermissionError, OSError) as exc:
        print(
            f"pretooluse-dispatcher: cannot run {name}: {exc!r}",
            file=sys.stderr,
        )
        return "", "", 0
    except Exception as exc:  # noqa: BLE001 — catch-all by design; isolation guarantee
        print(
            f"pretooluse-dispatcher: error in {name}: {exc!r}",
            file=sys.stderr,
        )
        return "", "", 0


def _passthrough(stdout: str, stderr: str, returncode: int, handler_name: str = "") -> None:
    """Write stdout to real stdout, stderr to real stderr, and exit with returncode.

    This is the blocking-guard contract: the output is byte-identical to
    running the guard directly — no JSON re-serialization, no wrapping.
    Handles both mechanism (a): stdout JSON + exit 0, and mechanism (b):
    stderr message + exit 2.

    An exit code outside the known contract (0, 2) is otherwise indistinguishable
    from a handler crash — emit a one-line advisory naming the handler and code
    so it's visible instead of silently passed through.
    """
    if returncode not in (0, 2):
        print(
            f"pretooluse-dispatcher: {handler_name or 'handler'} returned unexpected "
            f"exit code {returncode} (not 0 or 2) — possible crash, not an intentional block",
            file=sys.stderr,
        )
    if stdout:
        sys.stdout.write(stdout)
        sys.stdout.flush()
    if stderr:
        sys.stderr.write(stderr)
        sys.stderr.flush()
    sys.exit(returncode)


def main() -> None:
    if os.environ.get("CT_PRETOOLUSE_DISPATCHER_DISABLE") == "1":
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

    if tool_name == "Agent":
        # Path B fence (blocking): runs FIRST. If it blocks (stdout JSON or a
        # non-zero exit), pass through and STOP — codesight injection does not
        # run on a blocked dispatch. A missing or silent guard falls through
        # (_run_handler returns ("", "", 0) on FileNotFoundError / no output).
        if not _is_skipped(PAUL_AGENT_GUARD, skip):
            stdout, stderr, rc = _run_handler([sys.executable, PAUL_AGENT_GUARD], payload)
            if stdout.strip() or rc != 0:
                _passthrough(stdout, stderr, rc, Path(PAUL_AGENT_GUARD).name)

        # Codesight prompt injection: injects CODESIGHT_INSTRUCTION into the
        # Agent prompt via the updatedInput shape (runs only if guard was silent).
        if not _is_skipped(CODESIGHT_HOOKS, skip):
            stdout, stderr, rc = _run_handler([sys.executable, CODESIGHT_HOOKS], payload)
            if stdout.strip() or rc != 0:
                _passthrough(stdout, stderr, rc, Path(CODESIGHT_HOOKS).name)

    elif tool_name == "Read":
        # Read has no blocking guards — run the NON-blocking engram injector.
        # It is a context provider, NOT a guard: it must NEVER set the dispatcher's
        # exit code. A clean run (rc==0 + stdout) passes the envelope through; a
        # nonzero exit (an import/syntax error raised BEFORE the injector's own
        # __main__ try/except can catch it) is SWALLOWED so the dispatcher still
        # exits 0 and the Read proceeds.
        if not _is_skipped(ENGRAM_INJECT, skip):
            stdout, stderr, rc = _run_handler(
                [sys.executable, ENGRAM_INJECT], payload, timeout=5)
            if rc == 0 and stdout.strip():
                _passthrough(stdout, "", 0, Path(ENGRAM_INJECT).name)
            elif rc != 0:
                print(f"pretooluse-dispatcher: engram injector exit {rc} swallowed "
                      f"(non-blocking)", file=sys.stderr)
                # do NOT _passthrough — fall through so the dispatcher exits 0

    elif tool_name in ("Edit", "Write"):
        # Clean-tree completion gate (blocking) — runs FIRST (FIX 7). It is
        # SILENT except on a confirmed dirty-completion transition, so running
        # it before write-guard is safe: if silent, write-guard runs normally
        # next; if it blocks, the edit is blocked anyway. It MUST precede
        # write-guard because write-guard can emit a NON-blocking ALLOW advisory
        # (e.g. graduated Codex-learning C1 path-trust) on a plan status-flip
        # edit — and the dispatcher's first-response-wins passthrough would then
        # exit on that advisory's stdout before clean-tree ever ran, leaking a
        # dirty completion. (Confirmed against write-guard.py: check_c1_path_trust
        # is language-agnostic with no file-extension gate, and a Write flip
        # carries the full plan body, which is full of path tokens.)
        if not _is_skipped(CLEAN_TREE_GATE, skip):
            stdout, stderr, rc = _run_handler([sys.executable, CLEAN_TREE_GATE], payload)
            if stdout.strip() or rc != 0:
                _passthrough(stdout, stderr, rc, Path(CLEAN_TREE_GATE).name)

        # Write guard (blocking): pass stdout verbatim and exit if it produced output.
        if not _is_skipped(WRITE_GUARD, skip):
            stdout, stderr, rc = _run_handler([sys.executable, WRITE_GUARD], payload)
            if stdout.strip() or rc != 0:
                _passthrough(stdout, stderr, rc, Path(WRITE_GUARD).name)

        # Engram delivery injector (NON-blocking) — runs LAST, only if both blocking
        # guards above stayed silent. Emitting the additionalContext envelope is stdout
        # output, so under first-response-wins it MUST be last or it would pre-empt a
        # guard. (If write-guard emitted a non-blocking ALLOW advisory, its _passthrough
        # already exited above and the injector is correctly skipped for that call.)
        # Same swallow-crash contract as the Read branch: a nonzero injector exit must
        # NOT become the dispatcher's exit code (it would fail every Edit/Write).
        if not _is_skipped(ENGRAM_INJECT, skip):
            stdout, stderr, rc = _run_handler(
                [sys.executable, ENGRAM_INJECT], payload, timeout=5)
            if rc == 0 and stdout.strip():
                _passthrough(stdout, "", 0, Path(ENGRAM_INJECT).name)
            elif rc != 0:
                print(f"pretooluse-dispatcher: engram injector exit {rc} swallowed "
                      f"(non-blocking)", file=sys.stderr)
                # do NOT _passthrough — fall through so the dispatcher exits 0

    elif tool_name == "Bash":
        # Git safety guard (blocking) — runs first.
        # If it produces any output (block/advisory) or exits non-zero, pass through
        # and stop.
        if not _is_skipped(GIT_SAFETY_GUARD, skip):
            stdout, stderr, rc = _run_handler([sys.executable, GIT_SAFETY_GUARD], payload)
            if stdout.strip() or rc != 0:
                _passthrough(stdout, stderr, rc, Path(GIT_SAFETY_GUARD).name)

        # rtk hook claude — only runs if git-safety-guard was silent (no output).
        # rtk is a single matcher entry that previously ran independently as a
        # duplicate Bash entry; it is now collapsed here.
        if not _is_skipped("rtk", skip):
            rtk_bin = shutil.which("rtk")
            if rtk_bin:
                stdout, stderr, rc = _run_handler(
                    [rtk_bin, "hook", "claude"], payload, timeout=10
                )
                # Pass through rtk output and its exit code (rtk may exit non-zero).
                if stdout.strip() or rc != 0:
                    _passthrough(stdout, stderr, rc, "rtk")
            else:
                print(
                    "pretooluse-dispatcher: rtk not found on PATH; skipping",
                    file=sys.stderr,
                )

    # For all other tool names: no handlers registered — fall through to exit 0.


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise  # propagate sys.exit() calls from _passthrough and main()
    except Exception as exc:  # noqa: BLE001 — dispatcher crash must never block a tool call
        import traceback

        print(
            f"pretooluse-dispatcher: CRASH: {exc!r}\n{traceback.format_exc()}",
            file=sys.stderr,
        )
        sys.exit(0)
