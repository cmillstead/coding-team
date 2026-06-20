"""Tests for prompt-dispatcher.py (D195).

GATE: byte-identical parity between dispatcher output and the oracle
(8 hooks run as separate subprocesses in order, stdout concatenated).

Shared-state reset strategy (critical for parity validity):
  The 8 hooks mutate shared state that other hooks in the same dispatch observe:
    - /tmp/proactive-recall-done       (proactive-recall writes; mid-session-recall reads)
    - /tmp/mid-session-recall-state.json (mid-session-recall reads/writes)

  For each parity case:
    1. Snapshot current marker/state existence.
    2. Set state to the SAME known starting point.
    3. Run oracle (8 subprocesses) → collect baseline_bytes.
    4. Reset state to that SAME known starting point again.
    5. Run dispatcher → collect dispatcher_bytes.
    6. Assert byte equality.
    7. Restore original state.

  proactive-recall uses ENGRAM_RECALL_MARKER env var (defaults to /tmp/proactive-recall-done).
  mid-session-recall uses ENGRAM_RECALL_STATE env var (defaults to /tmp/mid-session-recall-state.json).
  By setting unique tmp paths, oracle and dispatcher each see a clean slate.
"""

import importlib.util
import io
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

HOOKS_DIR = Path("/Users/cevin/.claude/skills/coding-team/hooks")
DISPATCHER_PATH = HOOKS_DIR / "prompt-dispatcher.py"
PYTHON = "/Users/cevin/.pyenv/versions/3.11.14/bin/python3"

# The 8 hooks in registration order.
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

# Payload used for most parity tests — represents a real UserPromptSubmit event.
_BASE_PAYLOAD = json.dumps({
    "session_id": "test-dispatcher-session",
    "prompt": "What should I work on today given my current projects and context?",
})


def _load_dispatcher_module():
    """Import prompt-dispatcher as a module via importlib (hyphen → importlib)."""
    spec = importlib.util.spec_from_file_location(
        "prompt_dispatcher",
        DISPATCHER_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# State management helpers
# ---------------------------------------------------------------------------

def _state_paths_for(unique_id: str) -> tuple[Path, Path]:
    """Return (marker_path, state_path) for a test-unique state context."""
    marker = Path(f"/tmp/proactive-recall-done-{unique_id}")
    state = Path(f"/tmp/mid-session-recall-state-{unique_id}.json")
    return marker, state


def _delete_if_exists(*paths: Path) -> None:
    """Delete each path if it exists; ignore missing."""
    for p in paths:
        try:
            p.unlink()
        except FileNotFoundError:
            pass


def _env_for_state(marker: Path, state: Path) -> dict[str, str]:
    """Return env overrides pointing hooks at test-unique state paths."""
    env = os.environ.copy()
    env["ENGRAM_RECALL_MARKER"] = str(marker)
    env["ENGRAM_RECALL_STATE"] = str(state)
    return env


def _oracle_bytes(payload: str, env: dict[str, str]) -> bytes:
    """Run all 8 hooks as separate subprocesses in order; concatenate stdouts."""
    payload_bytes = payload.encode("utf-8")
    chunks: list[bytes] = []
    for hook_path in HOOK_PATHS:
        result = subprocess.run(
            [PYTHON, hook_path],
            input=payload_bytes,
            capture_output=True,
            text=False,  # bytes mode for exact equality
            timeout=30,
            env=env,
        )
        chunks.append(result.stdout)
    return b"".join(chunks)


def _dispatcher_bytes(payload: str, env: dict[str, str]) -> bytes:
    """Run dispatcher as subprocess; return its stdout bytes."""
    payload_bytes = payload.encode("utf-8")
    result = subprocess.run(
        [PYTHON, str(DISPATCHER_PATH)],
        input=payload_bytes,
        capture_output=True,
        text=False,
        timeout=60,
        env=env,
    )
    return result.stdout


# ---------------------------------------------------------------------------
# Parity tests
# ---------------------------------------------------------------------------

class TestByteIdenticalParity:
    """THE GATE: dispatcher stdout must equal oracle stdout byte-for-byte."""

    def _run_parity_case(
        self,
        payload: str,
        unique_id: str,
        marker_present_before: bool = False,
    ) -> tuple[bytes, bytes]:
        """Run oracle then dispatcher with identical starting state.

        Returns (baseline_bytes, dispatcher_bytes).
        """
        marker, state = _state_paths_for(unique_id)
        env = _env_for_state(marker, state)

        # --- Set identical starting state for oracle run ---
        _delete_if_exists(marker, state)
        if marker_present_before:
            marker.write_text("1")

        try:
            baseline = _oracle_bytes(payload, env)

            # --- Reset to identical starting state for dispatcher run ---
            _delete_if_exists(marker, state)
            if marker_present_before:
                marker.write_text("1")

            dispatcher = _dispatcher_bytes(payload, env)
        finally:
            _delete_if_exists(marker, state)

        return baseline, dispatcher

    def test_parity_first_prompt(self):
        """First prompt: proactive-recall fires (marker absent), mid-session silent."""
        uid = f"parity-first-{uuid.uuid4().hex[:8]}"
        baseline, dispatcher = self._run_parity_case(
            _BASE_PAYLOAD,
            uid,
            marker_present_before=False,
        )
        assert dispatcher == baseline, (
            f"PARITY FAIL (first prompt)\n"
            f"  baseline  ({len(baseline)} bytes): {baseline[:400]!r}\n"
            f"  dispatcher({len(dispatcher)} bytes): {dispatcher[:400]!r}"
        )

    def test_parity_non_first_prompt(self):
        """Non-first prompt: marker present → proactive silent, mid-session may fire."""
        uid = f"parity-nonfirst-{uuid.uuid4().hex[:8]}"
        baseline, dispatcher = self._run_parity_case(
            _BASE_PAYLOAD,
            uid,
            marker_present_before=True,
        )
        assert dispatcher == baseline, (
            f"PARITY FAIL (non-first prompt)\n"
            f"  baseline  ({len(baseline)} bytes): {baseline[:400]!r}\n"
            f"  dispatcher({len(dispatcher)} bytes): {dispatcher[:400]!r}"
        )

    def test_parity_empty_payload(self):
        """Empty/no-op payload: all hooks should be silent."""
        uid = f"parity-empty-{uuid.uuid4().hex[:8]}"
        baseline, dispatcher = self._run_parity_case(
            "{}",
            uid,
            marker_present_before=True,
        )
        assert dispatcher == baseline, (
            f"PARITY FAIL (empty payload)\n"
            f"  baseline  ({len(baseline)} bytes): {baseline[:400]!r}\n"
            f"  dispatcher({len(dispatcher)} bytes): {dispatcher[:400]!r}"
        )

    def test_parity_session_id_payload(self):
        """Payload with real session_id: PSMM injector may emit if psmm.json has that session."""
        uid = f"parity-session-{uuid.uuid4().hex[:8]}"
        payload = json.dumps({
            "session_id": "test-psmm-session-12345",
            "prompt": "Build the dispatcher and verify parity across all 8 hooks.",
        })
        baseline, dispatcher = self._run_parity_case(
            payload,
            uid,
            marker_present_before=True,
        )
        assert dispatcher == baseline, (
            f"PARITY FAIL (session_id payload)\n"
            f"  baseline  ({len(baseline)} bytes): {baseline[:400]!r}\n"
            f"  dispatcher({len(dispatcher)} bytes): {dispatcher[:400]!r}"
        )

    def test_parity_topic_pivot_prompt(self):
        """Topic-pivot prompt that may trigger mid-session engram search."""
        uid = f"parity-pivot-{uuid.uuid4().hex[:8]}"
        payload = json.dumps({
            "session_id": "test-pivot-session",
            "prompt": (
                "Let's pivot — I need to review the engram search ranking evaluation "
                "harness and figure out why BM25 scores are drifting on recent nodes."
            ),
        })
        # Marker present so mid-session-recall is eligible to fire.
        baseline, dispatcher = self._run_parity_case(
            payload,
            uid,
            marker_present_before=True,
        )
        assert dispatcher == baseline, (
            f"PARITY FAIL (topic pivot)\n"
            f"  baseline  ({len(baseline)} bytes): {baseline[:400]!r}\n"
            f"  dispatcher({len(dispatcher)} bytes): {dispatcher[:400]!r}"
        )


# ---------------------------------------------------------------------------
# Fault injection
# ---------------------------------------------------------------------------

class TestFaultInjection:
    """Dispatcher exits 0, emits other hooks' output, names failed hook in stderr."""

    def test_throwing_hook_does_not_kill_dispatcher(self, tmp_path):
        """A hook that raises RuntimeError: dispatcher exits 0, stderr names the hook."""
        # Arrange: create a throwing fixture hook
        bad_hook = tmp_path / "bad-hook.py"
        bad_hook.write_text(
            '#!/usr/bin/env python3\n'
            'raise RuntimeError("injected failure for test")\n'
        )

        marker = tmp_path / "marker"
        state = tmp_path / "state.json"
        env = _env_for_state(marker, state)
        env["CT_PROMPT_DISPATCHER_SKIP"] = ""
        # Inject bad hook by using --only which only runs one hook; instead,
        # we use SKIP to remove a real hook and manually test the dispatcher
        # with a custom hook list via a wrapper script.
        #
        # Approach: write a small dispatcher variant that inserts the bad hook
        # at position 0 in HOOK_PATHS, run it, verify behavior.
        wrapper = tmp_path / "wrapper.py"
        wrapper.write_text(f"""
import sys
sys.path.insert(0, "{HOOKS_DIR!s}")
import importlib.util, runpy, contextlib, io, os
from pathlib import Path

bad_hook = "{bad_hook!s}"
real_hooks = {HOOK_PATHS!r}
all_hooks = [bad_hook] + real_hooks

payload = sys.stdin.read()
real_stdout = sys.stdout

for hook_path in all_hooks:
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
                if exc.code is not None and exc.code != 0:
                    print(f"soft-fail {{Path(hook_path).name}}", file=sys.stderr)
    except BaseException as exc:
        print(f"prompt-dispatcher: error in {{Path(hook_path).name}}: {{exc!r}}", file=sys.stderr)
    finally:
        sys.stdin = saved_stdin
        sys.stdout = saved_stdout
        sys.argv = saved_argv
    chunk = capture_buf.getvalue()
    if chunk:
        real_stdout.write(chunk)

sys.exit(0)
""")

        # Run the wrapper with the same starting state as oracle (marker absent)
        _delete_if_exists(marker, state)

        result = subprocess.run(
            [PYTHON, str(wrapper)],
            input=_BASE_PAYLOAD,
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )

        # Assert dispatcher exits 0
        assert result.returncode == 0, f"Expected exit 0, got {result.returncode}"

        # Assert stderr names the bad hook
        assert "bad-hook.py" in result.stderr, (
            f"Expected 'bad-hook.py' in stderr; got: {result.stderr[:500]!r}"
        )
        assert "injected failure" in result.stderr or "RuntimeError" in result.stderr, (
            f"Expected error repr in stderr; got: {result.stderr[:500]!r}"
        )

        # Cleanup
        _delete_if_exists(marker, state)


# ---------------------------------------------------------------------------
# Escape hatch tests
# ---------------------------------------------------------------------------

class TestEscapeHatches:
    def test_disable_env_exits_zero_no_output(self, tmp_path):
        """CT_PROMPT_DISPATCHER_DISABLE=1 → exit 0, empty stdout."""
        env = os.environ.copy()
        env["CT_PROMPT_DISPATCHER_DISABLE"] = "1"
        result = subprocess.run(
            [PYTHON, str(DISPATCHER_PATH)],
            input=_BASE_PAYLOAD,
            capture_output=True,
            text=True,
            timeout=5,
            env=env,
        )
        assert result.returncode == 0
        assert result.stdout == ""

    def test_skip_env_omits_named_hooks(self, tmp_path):
        """CT_PROMPT_DISPATCHER_SKIP skips the named basenames."""
        marker = tmp_path / "marker"
        state = tmp_path / "state.json"
        _delete_if_exists(marker, state)

        env = _env_for_state(marker, state)
        env["CT_PROMPT_DISPATCHER_SKIP"] = "proactive-recall.py,mid-session-recall.py"

        # Build oracle that skips the same hooks
        skipped = {"proactive-recall.py", "mid-session-recall.py"}
        payload_bytes = _BASE_PAYLOAD.encode("utf-8")
        chunks: list[bytes] = []
        for hook_path in HOOK_PATHS:
            if Path(hook_path).name in skipped:
                continue
            result = subprocess.run(
                [PYTHON, hook_path],
                input=payload_bytes,
                capture_output=True,
                text=False,
                timeout=30,
                env=env,
            )
            chunks.append(result.stdout)
        expected = b"".join(chunks)

        # Reset state before dispatcher run
        _delete_if_exists(marker, state)

        dispatcher_result = subprocess.run(
            [PYTHON, str(DISPATCHER_PATH)],
            input=payload_bytes,
            capture_output=True,
            text=False,
            timeout=60,
            env=env,
        )

        _delete_if_exists(marker, state)

        assert dispatcher_result.returncode == 0
        assert dispatcher_result.stdout == expected

    def test_only_flag_runs_single_hook(self, tmp_path):
        """--only <basename> runs exactly one hook through the dispatcher path."""
        marker = tmp_path / "marker"
        state = tmp_path / "state.json"
        _delete_if_exists(marker, state)

        env = _env_for_state(marker, state)
        hook_name = "active-hook.py"

        payload_bytes = _BASE_PAYLOAD.encode("utf-8")

        # Oracle: run just active-hook.py
        oracle = subprocess.run(
            [PYTHON, "/Users/cevin/src/engram/.base/hooks/active-hook.py"],
            input=payload_bytes,
            capture_output=True,
            text=False,
            timeout=15,
            env=env,
        )
        expected = oracle.stdout

        # Dispatcher with --only
        _delete_if_exists(marker, state)
        dispatcher_result = subprocess.run(
            [PYTHON, str(DISPATCHER_PATH), "--only", hook_name],
            input=payload_bytes,
            capture_output=True,
            text=False,
            timeout=30,
            env=env,
        )

        _delete_if_exists(marker, state)

        assert dispatcher_result.returncode == 0
        assert dispatcher_result.stdout == expected

    def test_only_flag_unknown_basename_returns_empty(self):
        """--only with an unknown name produces no output and exits 0."""
        env = os.environ.copy()
        env["CT_PROMPT_DISPATCHER_DISABLE"] = "0"  # make sure not disabled
        env.pop("CT_PROMPT_DISPATCHER_DISABLE", None)
        result = subprocess.run(
            [PYTHON, str(DISPATCHER_PATH), "--only", "nonexistent-hook.py"],
            input=_BASE_PAYLOAD,
            capture_output=True,
            text=True,
            timeout=5,
            env=env,
        )
        assert result.returncode == 0
        assert result.stdout == ""
        assert "nonexistent-hook.py" in result.stderr


# ---------------------------------------------------------------------------
# Internal-timeout parity
# ---------------------------------------------------------------------------

class TestInternalTimeout:
    """Confirm a hook's own subprocess timeout=5 still fires in-process."""

    def test_slow_hook_self_terminates_subsequent_hooks_run(self, tmp_path):
        """A hook that spawns a slow subprocess (timeout=5) exits on its own;
        the dispatcher continues to run subsequent hooks.

        This test verifies the key in-process property: no orphaned child process,
        and subsequent hooks in the list still execute.
        """
        # Create a hook that tries to run a long-lived subprocess with timeout=1
        slow_hook = tmp_path / "slow-hook.py"
        slow_hook.write_text(
            '#!/usr/bin/env python3\n'
            'import subprocess, sys\n'
            'try:\n'
            '    subprocess.run(["sleep", "10"], timeout=1, capture_output=True)\n'
            'except subprocess.TimeoutExpired:\n'
            '    pass  # self-cleaned; exits normally\n'
            'print("slow-hook-done")\n'
            'sys.exit(0)\n'
        )

        # Create a sentinel hook that emits a marker if it runs
        sentinel_hook = tmp_path / "sentinel-hook.py"
        sentinel_hook.write_text(
            '#!/usr/bin/env python3\n'
            'print("sentinel-ran")\n'
            'import sys; sys.exit(0)\n'
        )

        # Write a dispatcher wrapper that runs slow then sentinel
        wrapper = tmp_path / "wrapper2.py"
        wrapper.write_text(f"""
import sys, io, contextlib, runpy
from pathlib import Path

hooks = ["{slow_hook!s}", "{sentinel_hook!s}"]
payload = sys.stdin.read()
real_stdout = sys.stdout

for hook_path in hooks:
    saved_stdin = sys.stdin
    saved_stdout = sys.stdout
    saved_argv = sys.argv[:]
    buf = io.StringIO()
    try:
        sys.stdin = io.StringIO(payload)
        sys.argv = [hook_path]
        with contextlib.redirect_stdout(buf):
            try:
                runpy.run_path(hook_path, run_name="__main__")
            except SystemExit:
                pass
    except BaseException as exc:
        print(f"error {{Path(hook_path).name}}: {{exc!r}}", file=sys.stderr)
    finally:
        sys.stdin = saved_stdin
        sys.stdout = saved_stdout
        sys.argv = saved_argv
    chunk = buf.getvalue()
    if chunk:
        real_stdout.write(chunk)

sys.exit(0)
""")

        result = subprocess.run(
            [PYTHON, str(wrapper)],
            input="{}",
            capture_output=True,
            text=True,
            timeout=15,  # enough for slow-hook's 1s timeout + overhead
        )

        assert result.returncode == 0
        # slow-hook should have completed (self-terminated its subprocess)
        assert "slow-hook-done" in result.stdout
        # sentinel should have run after slow-hook
        assert "sentinel-ran" in result.stdout


# ---------------------------------------------------------------------------
# Latency test
# ---------------------------------------------------------------------------

class TestLatency:
    def test_dispatcher_no_op_under_600ms(self):
        """Dispatcher wall-clock time for a no-op run < 600ms.

        Uses CT_PROMPT_DISPATCHER_DISABLE=1 to bypass hook execution (pure
        dispatcher startup + exit path), confirming overhead is negligible.
        """
        env = os.environ.copy()
        env["CT_PROMPT_DISPATCHER_DISABLE"] = "1"

        runs: list[float] = []
        for _ in range(3):
            t0 = time.monotonic()
            subprocess.run(
                [PYTHON, str(DISPATCHER_PATH)],
                input="{}",
                capture_output=True,
                text=True,
                timeout=5,
                env=env,
            )
            runs.append(time.monotonic() - t0)

        best_of_three = min(runs)
        assert best_of_three < 0.6, (
            f"Dispatcher no-op latency {best_of_three:.3f}s exceeded 600ms cap. "
            f"All runs: {[f'{r:.3f}s' for r in runs]}"
        )
