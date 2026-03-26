"""Tests for test-gap-correction.py hook."""
from pathlib import Path

HOOK = "test-gap-correction.py"
HOOKS_DIR = Path("/Users/cevin/.claude/skills/coding-team/hooks")


class TestNonHookFileEdit:
    def test_non_hook_file_no_output(self, run_hook, make_event):
        """Editing a random Python file outside hooks/ produces no output."""
        event = make_event("Edit", file_path="/Users/cevin/src/app/main.py")
        result = run_hook(HOOK, event)
        assert result.stdout.strip() == ""

    def test_non_python_file_no_output(self, run_hook, make_event):
        """Editing a non-.py file produces no output."""
        event = make_event("Write", file_path=str(HOOKS_DIR / "deploy.sh"))
        result = run_hook(HOOK, event)
        assert result.stdout.strip() == ""

    def test_bash_tool_ignored(self, run_hook, make_event):
        """Only Write/Edit tools trigger the hook."""
        event = make_event("Bash", command="python3 hooks/some-hook.py")
        result = run_hook(HOOK, event)
        assert result.stdout.strip() == ""


class TestHookWithExistingTest:
    def test_hook_with_test_no_output(self, run_hook, make_event):
        """Editing a hook that already has a test file produces no output."""
        # test-gap-correction.py itself has test_test_gap_correction.py
        event = make_event("Edit", file_path=str(HOOKS_DIR / "test-gap-correction.py"))
        result = run_hook(HOOK, event)
        assert result.stdout.strip() == ""

    def test_deliverable_correction_has_test(self, run_hook, make_event):
        """deliverable-correction.py has its test file, so no advisory."""
        event = make_event("Edit", file_path=str(HOOKS_DIR / "deliverable-correction.py"))
        result = run_hook(HOOK, event)
        assert result.stdout.strip() == ""


class TestHookMissingTest:
    def test_missing_test_emits_advisory(self, run_hook, make_event, tmp_path):
        """Editing a hook with no test file emits an advisory."""
        # Create a fake hook file in a hooks/ directory inside tmp_path
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        fake_hook = hooks_dir / "brand-new-hook.py"
        fake_hook.write_text("# hook")

        event = make_event("Write", file_path=str(fake_hook))
        result = run_hook(HOOK, event)
        assert result.parsed is not None
        assert result.parsed["decision"] == "allow"
        assert "TEST GAP" in result.parsed["reason"]
        assert "brand-new-hook.py" in result.parsed["reason"]
        assert "test_brand_new_hook.py" in result.parsed["reason"]

    def test_advisory_includes_rationalization(self, run_hook, make_event, tmp_path):
        """Advisory must include the named rationalization."""
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        fake_hook = hooks_dir / "untested-hook.py"
        fake_hook.write_text("# hook")

        event = make_event("Write", file_path=str(fake_hook))
        result = run_hook(HOOK, event)
        assert result.parsed is not None
        assert "follow-up" in result.parsed["reason"]


class TestLibFilesSkipped:
    def test_lib_file_no_output(self, run_hook, make_event):
        """Files inside _lib/ are not hooks and should be skipped."""
        event = make_event("Edit", file_path=str(HOOKS_DIR / "_lib" / "event.py"))
        result = run_hook(HOOK, event)
        assert result.stdout.strip() == ""

    def test_lib_output_no_output(self, run_hook, make_event):
        """_lib/output.py is not a hook."""
        event = make_event("Edit", file_path=str(HOOKS_DIR / "_lib" / "output.py"))
        result = run_hook(HOOK, event)
        assert result.stdout.strip() == ""


class TestTestsDirectorySkipped:
    def test_test_file_no_output(self, run_hook, make_event):
        """Files inside tests/ are not hooks and should be skipped."""
        event = make_event("Edit", file_path=str(HOOKS_DIR / "tests" / "test_foo.py"))
        result = run_hook(HOOK, event)
        assert result.stdout.strip() == ""

    def test_conftest_no_output(self, run_hook, make_event):
        """conftest.py inside tests/ is not a hook."""
        event = make_event("Edit", file_path=str(HOOKS_DIR / "tests" / "conftest.py"))
        result = run_hook(HOOK, event)
        assert result.stdout.strip() == ""


class TestShellScriptsSkipped:
    def test_shell_script_no_output(self, run_hook, make_event):
        """Shell scripts (.sh) don't need Python tests."""
        event = make_event("Write", file_path=str(HOOKS_DIR / "deploy.sh"))
        result = run_hook(HOOK, event)
        assert result.stdout.strip() == ""
