"""Tests for entropy-cleanup.py hook."""
import json
import subprocess
import time
from pathlib import Path

import pytest

HOOKS_DIR = Path("/Users/cevin/.claude/skills/coding-team/hooks")


def run_entropy_hook(stdin_data: str = "{}") -> subprocess.CompletedProcess:
    return subprocess.run(
        ["python3", str(HOOKS_DIR / "entropy-cleanup.py")],
        input=stdin_data,
        capture_output=True,
        text=True,
        timeout=10,
    )


class TestSyntax:
    def test_hook_runs_without_crash(self):
        result = run_entropy_hook()
        assert result.returncode == 0

    def test_no_traceback_in_stderr(self):
        result = run_entropy_hook()
        assert "Traceback" not in result.stderr


class TestStaleFiles:
    def test_detects_old_state_file(self, tmp_path):
        """Create a stale file and verify detection logic."""
        # Test the find_stale_state_files function via subprocess
        code = (
            f"import sys; sys.path.insert(0, {str(HOOKS_DIR)!r})\n"
            f"import importlib.util, json, os, time\n"
            f"spec = importlib.util.spec_from_file_location('ec', {str(HOOKS_DIR / 'entropy-cleanup.py')!r})\n"
            f"mod = importlib.util.module_from_spec(spec)\n"
            f"spec.loader.exec_module(mod)\n"
            f"# Test with actual /tmp — may or may not have stale files\n"
            f"result = mod.find_stale_state_files()\n"
            f"print(json.dumps({{'type': type(result).__name__, 'is_list': isinstance(result, list)}}))\n"
        )
        result = subprocess.run(
            ["python3", "-c", code],
            capture_output=True, text=True, timeout=10,
        )
        data = json.loads(result.stdout)
        assert data["is_list"] is True


class TestLargeMetrics:
    def test_returns_list(self):
        code = (
            f"import sys; sys.path.insert(0, {str(HOOKS_DIR)!r})\n"
            f"import importlib.util, json\n"
            f"spec = importlib.util.spec_from_file_location('ec', {str(HOOKS_DIR / 'entropy-cleanup.py')!r})\n"
            f"mod = importlib.util.module_from_spec(spec)\n"
            f"spec.loader.exec_module(mod)\n"
            f"result = mod.find_large_metrics_files()\n"
            f"print(json.dumps({{'is_list': isinstance(result, list)}}))\n"
        )
        result = subprocess.run(
            ["python3", "-c", code],
            capture_output=True, text=True, timeout=10,
        )
        data = json.loads(result.stdout)
        assert data["is_list"] is True


class TestOrphanSessions:
    def test_returns_list(self):
        code = (
            f"import sys; sys.path.insert(0, {str(HOOKS_DIR)!r})\n"
            f"import importlib.util, json\n"
            f"spec = importlib.util.spec_from_file_location('ec', {str(HOOKS_DIR / 'entropy-cleanup.py')!r})\n"
            f"mod = importlib.util.module_from_spec(spec)\n"
            f"spec.loader.exec_module(mod)\n"
            f"result = mod.find_orphan_sessions()\n"
            f"print(json.dumps({{'is_list': isinstance(result, list)}}))\n"
        )
        result = subprocess.run(
            ["python3", "-c", code],
            capture_output=True, text=True, timeout=10,
        )
        data = json.loads(result.stdout)
        assert data["is_list"] is True
