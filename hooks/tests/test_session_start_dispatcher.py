"""Tests for session-start-dispatcher.py.

Verify the consolidation invariants the brief requires:
  - per-check isolation: one crashing sub-check does not suppress the others
  - legacy decision/result JSON envelopes are unwrapped to plain text
  - plain-text output is passed through verbatim
  - all surviving check outputs are concatenated and surfaced
  - the dispatcher always exits 0 and emits PLAIN TEXT (never the decision JSON)
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

_HOOKS = Path("/Users/cevin/.claude/skills/coding-team/hooks")
_DISPATCHER = _HOOKS / "session-start-dispatcher.py"

# Load the dispatcher module by path (filename has a hyphen → not importable).
_spec = importlib.util.spec_from_file_location("ssd", _DISPATCHER)
ssd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ssd)


def test_unwrap_decision_envelope_returns_reason():
    text = '{"decision": "allow", "reason": "hello world"}'
    assert ssd._unwrap_legacy_envelope(text) == "hello world"


def test_unwrap_result_envelope_returns_message():
    text = '{"result": "allow", "message": "weekly synth due"}'
    assert ssd._unwrap_legacy_envelope(text) == "weekly synth due"


def test_unwrap_empty_decision_envelope_returns_empty():
    assert ssd._unwrap_legacy_envelope('{"decision": "allow"}') == ""


def test_plaintext_passed_through_verbatim():
    text = "Context staleness check: 2 items\n  foo\n  bar"
    assert ssd._unwrap_legacy_envelope(text) == text


def test_non_envelope_json_passed_through():
    # JSON that is not a recognized envelope is preserved verbatim.
    text = '{"some": "other", "shape": 1}'
    assert ssd._unwrap_legacy_envelope(text) == text


def test_malformed_json_passed_through():
    text = '{not valid json'
    assert ssd._unwrap_legacy_envelope(text) == text


def _make_check(tmp_path, name, body):
    p = tmp_path / name
    p.write_text("#!/usr/bin/env python3\n" + body)
    return p


def test_run_check_crashing_returns_empty(tmp_path):
    crash = _make_check(tmp_path, "crash.py", "import sys; sys.exit(2)\nraise SystemExit\n")
    out = ssd._run_check([sys.executable, str(crash)], 5)
    assert out == ""


def test_run_check_timeout_returns_empty(tmp_path):
    slow = _make_check(tmp_path, "slow.py", "import time; time.sleep(10)\n")
    out = ssd._run_check([sys.executable, str(slow)], 1)
    assert out == ""


def test_run_check_missing_interpreter_returns_empty():
    out = ssd._run_check(["/no/such/interp", "/no/such/script.py"], 5)
    assert out == ""


def test_run_check_unwraps_decision_json(tmp_path):
    emit = _make_check(
        tmp_path, "emit.py",
        "print('{\"decision\": \"allow\", \"reason\": \"surfaced text\"}')\n",
    )
    out = ssd._run_check([sys.executable, str(emit)], 5)
    assert out == "surfaced text"


def test_isolation_one_crash_does_not_suppress_others(tmp_path, monkeypatch):
    """A crashing check between two healthy checks must not drop their output."""
    good1 = _make_check(tmp_path, "g1.py", "print('FIRST')\n")
    crash = _make_check(tmp_path, "c.py", "raise SystemExit(3)\n")
    good2 = _make_check(tmp_path, "g2.py", "print('SECOND')\n")

    monkeypatch.setattr(ssd, "_checks", lambda: [
        ([sys.executable, str(good1)], 5),
        ([sys.executable, str(crash)], 5),
        ([sys.executable, str(good2)], 5),
    ])

    import io
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    monkeypatch.setattr(sys, "stdout", buf)
    try:
        ssd.main()
    except SystemExit:
        pass
    output = buf.getvalue()
    assert "FIRST" in output
    assert "SECOND" in output


def test_dispatcher_emits_plain_text_not_decision_json():
    """End-to-end: dispatcher stdout must be plain text, never a decision envelope."""
    result = subprocess.run(
        [sys.executable, str(_DISPATCHER)],
        input="{}",
        capture_output=True,
        text=True,
        timeout=60,
        env={"CT_SESSION_DISPATCHER_DISABLE": "1", "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0
    assert result.stdout == ""  # disabled → no output


def test_dispatcher_skip_env_excludes_named_check(tmp_path, monkeypatch):
    good = _make_check(tmp_path, "keep.py", "print('KEEP')\n")
    skipd = _make_check(tmp_path, "drop.py", "print('DROP')\n")
    monkeypatch.setattr(ssd, "_checks", lambda: [
        ([sys.executable, str(good)], 5),
        ([sys.executable, str(skipd)], 5),
    ])
    monkeypatch.setenv("CT_SESSION_DISPATCHER_SKIP", "drop.py")
    import io
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    monkeypatch.setattr(sys, "stdout", buf)
    try:
        ssd.main()
    except SystemExit:
        pass
    out = buf.getvalue()
    assert "KEEP" in out
    assert "DROP" not in out
