#!/usr/bin/env python3
"""Builder self-validation hook: PostToolUse on Edit/Write.

Runs language-appropriate checks after the builder edits a file:
1. Python: ruff check + mypy (if available)
2. TypeScript/JavaScript: tsc --noEmit (if tsconfig exists)
3. Test files: run the specific test file
4. Any failure: deferred to LOG_FILE (never blocks the hot path)

This hook fires and forgets — checks run in a detached background worker.
Findings are appended to LOG_FILE; nothing is emitted inline on the hot path.
"""

import os
import re
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))

from _lib import event as _event
from _lib import output as _output

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
LOG_FILE = "/tmp/builder-self-check.log"

TEST_FILE_PATTERNS = [
    r'test[s]?[/_]',
    r'_test\.',
    r'\.test\.',
    r'\.spec\.',
    r'test_\w+\.',
]

PYTHON_EXTENSIONS = {".py"}
TS_JS_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx"}


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def _log(message: str) -> None:
    """Append a timestamped message to the validation log."""
    try:
        with open(LOG_FILE, "a") as fh:
            fh.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# File classification
# ---------------------------------------------------------------------------
def _get_extension(file_path: str) -> str:
    """Return the lowercased file extension."""
    _, ext = os.path.splitext(file_path)
    return ext.lower()


def _is_test_file(file_path: str) -> bool:
    """Check if a file path matches test file patterns.

    Matches against the filename only (not the full path) to avoid
    false positives from directory names containing 'test'.
    """
    filename = os.path.basename(file_path)
    return any(re.search(p, filename) for p in TEST_FILE_PATTERNS)


def _find_tsconfig(file_path: str) -> str | None:
    """Walk up from file_path looking for tsconfig.json. Return path or None."""
    from pathlib import Path

    current = Path(file_path).parent
    for _ in range(10):  # max 10 levels up
        candidate = current / "tsconfig.json"
        if candidate.exists():
            return str(candidate)
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


# ---------------------------------------------------------------------------
# Check runners
# ---------------------------------------------------------------------------
def _run_ruff(file_path: str) -> str | None:
    """Run ruff check on a Python file. Return error output or None."""
    if not shutil.which("ruff"):
        _log("ruff not found, skipping")
        return None

    try:
        result = subprocess.run(
            ["ruff", "check", file_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        _log(f"ruff timed out on {file_path}")
        return None
    except FileNotFoundError:
        return None

    if result.returncode != 0 and result.stdout.strip():
        _log(f"ruff found issues in {file_path}")
        return result.stdout.strip()
    return None


def _run_mypy(file_path: str) -> str | None:
    """Run mypy on a Python file. Return error output or None."""
    if not shutil.which("mypy"):
        _log("mypy not found, skipping")
        return None

    try:
        result = subprocess.run(
            ["mypy", "--no-error-summary", file_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        _log(f"mypy timed out on {file_path}")
        return None
    except FileNotFoundError:
        return None

    if result.returncode != 0 and result.stdout.strip():
        # Filter out "Success" lines
        lines = [
            line for line in result.stdout.strip().splitlines()
            if "Success" not in line
        ]
        if lines:
            _log(f"mypy found issues in {file_path}")
            return "\n".join(lines)
    return None


def _run_tsc(file_path: str) -> str | None:
    """Run tsc --noEmit if tsconfig.json exists nearby. Return error output or None."""
    tsconfig = _find_tsconfig(file_path)
    if not tsconfig:
        _log(f"no tsconfig.json found for {file_path}, skipping tsc")
        return None

    if not shutil.which("npx"):
        _log("npx not found, skipping tsc")
        return None

    try:
        result = subprocess.run(
            ["npx", "tsc", "--noEmit", "--project", tsconfig],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        _log(f"tsc timed out on {file_path}")
        return None
    except FileNotFoundError:
        return None

    if result.returncode != 0 and result.stdout.strip():
        # Only include errors related to the edited file
        relevant = [
            line for line in result.stdout.strip().splitlines()
            if os.path.basename(file_path) in line or line.startswith(" ")
        ]
        if relevant:
            _log(f"tsc found issues related to {file_path}")
            return "\n".join(relevant[:20])  # cap output length
    return None


def _run_test_file(file_path: str) -> str | None:
    """Run a test file directly. Return error output or None."""
    ext = _get_extension(file_path)

    if ext == ".py":
        runner = shutil.which("pytest")
        if not runner:
            runner = shutil.which("python3")
            if not runner:
                return None
            cmd = [runner, "-m", "pytest", file_path, "-x", "--tb=short", "-q"]
        else:
            cmd = [runner, file_path, "-x", "--tb=short", "-q"]
    elif ext in {".ts", ".tsx"}:
        # Try jest or vitest
        if shutil.which("npx"):
            cmd = ["npx", "jest", "--bail", file_path]
        else:
            return None
    else:
        return None

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        _log(f"test runner timed out on {file_path}")
        return None
    except FileNotFoundError:
        return None

    # Exit code 5 = no tests collected (pytest), not a real failure
    if result.returncode not in (0, 5):
        output = (result.stdout + "\n" + result.stderr).strip()
        if output:
            _log(f"test failures in {file_path}")
            # Cap output to avoid flooding the advisory
            lines = output.splitlines()
            if len(lines) > 30:
                lines = lines[:30] + [f"... ({len(lines) - 30} more lines)"]
            return "\n".join(lines)
    return None


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------
def _spawn_background_worker(file_path: str) -> None:
    """Fire-and-forget: run checks in a detached process; results land in LOG_FILE."""
    try:
        subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), "--worker", file_path],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        _log(f"could not spawn background worker for {file_path}")


def _run_worker(file_path: str) -> None:
    """Detached worker: run the existing checks and log findings (never block)."""
    ext = _get_extension(file_path)
    findings: list[str] = []
    if ext in PYTHON_EXTENSIONS:
        for runner, label in ((_run_ruff, "ruff"), (_run_mypy, "mypy")):
            out = runner(file_path)
            if out:
                findings.append(f"{label} found issues:\n{out}")
    if ext in TS_JS_EXTENSIONS:
        out = _run_tsc(file_path)
        if out:
            findings.append(f"tsc --noEmit found issues:\n{out}")
    if _is_test_file(file_path):
        out = _run_test_file(file_path)
        if out:
            findings.append(f"Test execution failed:\n{out}")
    if findings:
        _log("BUILDER SELF-CHECK (deferred): " + "\n\n".join(findings))
    else:
        _log(f"All deferred checks passed for {file_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    # Worker mode: run checks in background and log findings
    if len(sys.argv) >= 3 and sys.argv[1] == "--worker":
        _run_worker(sys.argv[2])
        return

    event = _event.parse_event()
    if not event:
        return

    tool_name = _event.get_tool_name(event)
    if tool_name not in ("Edit", "Write"):
        return

    tool_input = _event.get_tool_input(event)
    file_path = tool_input.get("file_path", "")
    if not file_path:
        return

    # Fire-and-forget: spawn detached worker; hot path returns immediately
    _spawn_background_worker(file_path)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Advisory hook — on crash, return silently (don't block)
        _log(f"CRASH: {__import__('traceback').format_exc()}")
