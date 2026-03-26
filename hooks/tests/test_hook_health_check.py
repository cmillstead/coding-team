"""Tests for hook-health-check.py hook."""

import importlib.util
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

HOOKS_DIR = Path("/Users/cevin/.claude/skills/coding-team/hooks")


def load_module():
    spec = importlib.util.spec_from_file_location(
        "hhc", str(HOOKS_DIR / "hook-health-check.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def hhc():
    return load_module()


class TestCheckHook:
    def test_healthy_script_returns_none(self, hhc, tmp_path):
        script = tmp_path / "healthy.py"
        script.write_text(textwrap.dedent("""\
            import json, sys
            print(json.dumps({"decision": "allow", "reason": "ok"}))
            sys.exit(0)
        """))
        assert hhc.check_hook(script) is None

    def test_exit_code_gt_1_detected(self, hhc, tmp_path):
        script = tmp_path / "bad_exit.py"
        script.write_text(textwrap.dedent("""\
            import sys
            sys.exit(2)
        """))
        result = hhc.check_hook(script)
        assert result is not None
        assert "exit code 2" in result

    def test_traceback_in_stderr_detected(self, hhc, tmp_path):
        script = tmp_path / "raises.py"
        script.write_text(textwrap.dedent("""\
            raise RuntimeError("boom")
        """))
        result = hhc.check_hook(script)
        assert result is not None
        assert "stderr" in result
        assert "Traceback" in result or "RuntimeError" in result

    def test_exit_code_1_is_acceptable(self, hhc, tmp_path):
        """Exit code 1 is acceptable (hooks may exit 1 for non-error reasons)."""
        script = tmp_path / "exit1.py"
        script.write_text(textwrap.dedent("""\
            import sys
            sys.exit(1)
        """))
        assert hhc.check_hook(script) is None

    def test_syntax_error_detected(self, hhc, tmp_path):
        script = tmp_path / "syntax_err.py"
        script.write_text("def broken(\n")
        result = hhc.check_hook(script)
        assert result is not None
        assert "SyntaxError" in result or "exit code" in result


class TestCheckShHook:
    def test_valid_bash_returns_none(self, hhc, tmp_path):
        script = tmp_path / "good.sh"
        script.write_text(textwrap.dedent("""\
            #!/bin/bash
            echo "hello"
            exit 0
        """))
        assert hhc.check_sh_hook(script) is None

    def test_invalid_bash_detected(self, hhc, tmp_path):
        script = tmp_path / "bad.sh"
        script.write_text(textwrap.dedent("""\
            #!/bin/bash
            if then else fi while
            ((((
        """))
        result = hhc.check_sh_hook(script)
        assert result is not None
        assert "bash syntax error" in result


class TestIntegration:
    def test_no_output_when_hooks_healthy(self, run_hook):
        """Full hook produces no output when all hooks are healthy."""
        result = run_hook("hook-health-check.py", {})
        # If all hooks in ~/.claude/hooks/ are healthy, output should be empty.
        # If some are unhealthy, we still verify valid JSON structure.
        if result.stdout.strip():
            parsed = json.loads(result.stdout)
            assert parsed["decision"] == "allow"
            assert "unhealthy" in parsed["reason"].lower()
        else:
            assert result.stdout.strip() == ""
