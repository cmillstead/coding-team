#!/usr/bin/env python3
"""SessionStart hook dispatcher.

Consolidates the six SessionStart checks that previously registered as six
separate entries under the matcher-"" block in ~/.claude/settings.json into a
single registration, mirroring the prompt-dispatcher.py precedent (which fronts
the UserPromptSubmit checks).

Why subprocess (not runpy like prompt-dispatcher):
  The six checks use THREE different interpreters and one lives OUTSIDE
  ~/.claude. They cannot all be imported in-process:
    - ci-orphan-detector.sh is bash, not Python.
    - satellite-detection.py must run from ~/src/engram/.base/hooks/ and uses a
      pyenv-shim python3 (its __file__-relative path resolution depends on its
      real on-disk location).
    - weekly-synthesis-check.py runs under a specific pyenv 3.11.14 interpreter.
  Each sub-check therefore runs as its own subprocess with its ORIGINAL
  interpreter and path, exactly as settings.json invoked it before.

Per-check isolation contract (the #1 consolidation risk):
  - Each sub-check runs in its own subprocess inside its own try/except.
  - A crash, non-zero exit, or timeout in one check NEVER prevents the other
    five from running (previously, six independent settings.json entries each
    ran regardless of the others; this dispatcher preserves that property).
  - Each sub-check has its own per-check timeout so one slow check cannot hang
    session start.

Output contract (SessionStart = PLAIN TEXT, never the decision JSON):
  SessionStart hooks must emit PLAIN TEXT to stdout, NOT the PreToolUse
  {"decision":"allow","reason":...} protocol. Emitting that JSON makes Claude
  Code report "SessionStart:startup hook error". Two of the six legacy checks
  (hook-health-check.py, ci-orphan-detector.sh) currently emit that malformed
  envelope, and weekly-synthesis-check.py emits {"result":"allow","message":...}.
  This dispatcher UNWRAPS any such legacy envelope to its plain-text payload, so
  every check's surfaced content is preserved while the malformed-protocol error
  is eliminated. Non-envelope plain-text output is passed through verbatim.

The dispatcher concatenates the (unwrapped) stdout of every sub-check and ALWAYS
exits 0 — a SessionStart context hook must never block or error the session.

Escape hatches (mirror prompt-dispatcher):
  CT_SESSION_DISPATCHER_DISABLE=1   -> exit 0 immediately, no output.
  CT_SESSION_DISPATCHER_SKIP="a,b"  -> skip checks whose basename matches a name.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

HOME = Path(os.path.expanduser("~"))
CLAUDE_HOOKS = HOME / ".claude" / "hooks"

# Interpreter resolution for the two pyenv-pinned checks. We resolve the pinned
# interpreters but degrade to a sane fallback if the exact path is absent, so a
# pyenv reshuffle cannot silently drop a check.
_PYENV_SHIM = Path("/Users/cevin/.pyenv/shims/python3")
_PYENV_3_11 = Path("/Users/cevin/.pyenv/versions/3.11.14/bin/python3")


def _interp(preferred: Path) -> str:
    """Return the preferred interpreter if it exists, else the dispatcher's own."""
    return str(preferred) if preferred.exists() else sys.executable


# Registration order is preserved from the old settings.json SessionStart block.
# Each entry: (argv, per_check_timeout_seconds). argv[0] is the interpreter; the
# original interpreter/path of every check is preserved exactly.
def _checks() -> list[tuple[list[str], int]]:
    return [
        # 1. hook-health-check.py — structural hook health + metrics analysis.
        ([sys.executable, str(CLAUDE_HOOKS / "hook-health-check.py")], 15),
        # 2. deploy-drift-check.py — source<->deployed hook drift.
        ([sys.executable, str(CLAUDE_HOOKS / "deploy-drift-check.py")], 10),
        # 3. ci-orphan-detector.sh — bash: orphan PRs + stale branches.
        (["bash", str(CLAUDE_HOOKS / "ci-orphan-detector.sh")], 30),
        # 4. satellite-detection.py — OUTSIDE ~/.claude; pyenv shim; __file__-relative.
        ([_interp(_PYENV_SHIM),
          "/Users/cevin/src/engram/.base/hooks/satellite-detection.py"], 15),
        # 5. context-staleness-check.py — stale _context.md + active-projects sync.
        ([sys.executable, str(CLAUDE_HOOKS / "context-staleness-check.py")], 10),
        # 6. weekly-synthesis-check.py — pyenv 3.11.14; weekly-synthesis reminder.
        ([_interp(_PYENV_3_11), str(CLAUDE_HOOKS / "weekly-synthesis-check.py")], 10),
    ]


def _unwrap_legacy_envelope(text: str) -> str:
    """If `text` is a legacy decision/result JSON envelope, return its payload.

    SessionStart output must be plain text. Some legacy checks emit the
    PreToolUse-style {"decision":"allow","reason":"..."} or the
    {"result":"allow","message":"..."} shape. We unwrap those to the inner
    human-readable string. Anything that is not exactly such an envelope is
    returned UNCHANGED (verbatim pass-through) — we never drop content.
    """
    stripped = text.strip()
    if not stripped or stripped[0] != "{":
        return text
    try:
        obj = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return text  # not JSON → pass through verbatim
    if not isinstance(obj, dict):
        return text
    # Recognized legacy envelopes: surface the reason/message payload as plaintext.
    for key in ("reason", "message"):
        val = obj.get(key)
        if isinstance(val, str) and val:
            return val
    # A decision/result envelope with no payload (e.g. {"decision":"allow"}) is
    # advisory-empty — emit nothing rather than the raw JSON.
    if obj.get("decision") in ("allow", "block") or obj.get("result") == "allow":
        return ""
    return text  # unknown JSON → pass through verbatim


def _run_check(argv: list[str], timeout: int) -> str:
    """Run one sub-check as a subprocess; return its (unwrapped) stdout.

    Fully isolated: any failure (crash, non-zero exit, timeout, missing
    interpreter, OS error) yields a one-line stderr note and an empty string, so
    the dispatcher continues to the next check. Never raises.
    """
    name = Path(argv[-1]).name
    try:
        result = subprocess.run(
            argv,
            input="{}",
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        print(f"session-start-dispatcher: timeout {name} after {timeout}s",
              file=sys.stderr)
        return ""
    except (FileNotFoundError, OSError) as exc:
        print(f"session-start-dispatcher: cannot run {name}: {exc!r}",
              file=sys.stderr)
        return ""
    except Exception as exc:  # noqa: BLE001 — catch-all by design; isolation guarantee
        print(f"session-start-dispatcher: error in {name}: {exc!r}",
              file=sys.stderr)
        return ""

    # A non-zero exit is not fatal — the check may legitimately reject empty
    # input. Surface a stderr breadcrumb but keep any stdout it produced.
    if result.returncode not in (0, 1) and result.stderr.strip():
        print(f"session-start-dispatcher: {name} exit {result.returncode}: "
              f"{result.stderr.strip()[:200]}", file=sys.stderr)

    return _unwrap_legacy_envelope(result.stdout or "")


def main() -> None:
    if os.environ.get("CT_SESSION_DISPATCHER_DISABLE") == "1":
        sys.exit(0)

    skip_env = os.environ.get("CT_SESSION_DISPATCHER_SKIP", "")
    skip_names = {n.strip() for n in skip_env.split(",") if n.strip()}

    # Drain stdin once (the hook contract passes a JSON event; sub-checks each get
    # a fresh "{}" — none of the six reads meaningful fields from the event).
    try:
        sys.stdin.read()
    except OSError:
        pass

    chunks: list[str] = []
    for argv, timeout in _checks():
        if Path(argv[-1]).name in skip_names:
            continue
        out = _run_check(argv, timeout)
        if out and out.strip():
            chunks.append(out.rstrip("\n"))

    if chunks:
        sys.stdout.write("\n\n".join(chunks) + "\n")

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 — a SessionStart hook must never break startup
        pass
    sys.exit(0)
