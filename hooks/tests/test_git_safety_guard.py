"""Tests for git-safety-guard.py hook."""

import hashlib
import json
import os
import time
from pathlib import Path


def _seed_verification_state(session_id: str, *, test_exit_code=None, lint_exit_code=None):
    """Seed verification state so commit format checks are reached.

    Args:
        session_id: The CLAUDE_SESSION_ID used for state file naming.
        test_exit_code: Exit code for the test command (None = unknown).
        lint_exit_code: Exit code for the lint command (None = unknown).
    """
    session_hash = hashlib.sha256(session_id.encode()).hexdigest()[:12]
    state_file = Path(f"/tmp/claude-verification-{session_hash}.json")
    now = time.time()
    state_file.write_text(json.dumps({
        "verifications": [
            {"command": "pytest tests/", "time": now, "exit_code": test_exit_code},
            {"command": "ruff check .", "time": now, "exit_code": lint_exit_code},
        ],
        "last_updated": now,
    }))


class TestSecretGuard:
    def test_blocks_git_add_env(self, run_hook, make_event):
        event = make_event("Bash", command="git add .env")
        result = run_hook("git-safety-guard.py", event)
        assert result.parsed is not None
        assert result.parsed["decision"] == "block"
        assert "secret" in result.parsed["reason"].lower()

    def test_blocks_git_add_credentials(self, run_hook, make_event):
        event = make_event("Bash", command="git add credentials.json")
        result = run_hook("git-safety-guard.py", event)
        assert result.parsed is not None
        assert result.parsed["decision"] == "block"
        assert "secret" in result.parsed["reason"].lower() or "credential" in result.parsed["reason"].lower()


class TestBroadAddGuard:
    def test_blocks_git_add_all(self, run_hook, make_event):
        event = make_event("Bash", command="git add -A")
        result = run_hook("git-safety-guard.py", event)
        assert result.parsed is not None
        assert result.parsed["decision"] == "block"
        assert "broad" in result.parsed["reason"].lower() or "git add" in result.parsed["reason"].lower()


class TestAllowedCommands:
    def test_allows_git_add_specific_file(self, run_hook, make_event):
        event = make_event("Bash", command="git add src/main.py")
        result = run_hook("git-safety-guard.py", event)
        # Should produce no output (silent allow)
        assert result.stdout.strip() == ""

    def test_allows_git_status(self, run_hook, make_event):
        event = make_event("Bash", command="git status")
        result = run_hook("git-safety-guard.py", event)
        assert result.stdout.strip() == ""

    def test_allows_non_bash_tool(self, run_hook, make_event):
        event = make_event("Read", file_path="/some/file.py")
        result = run_hook("git-safety-guard.py", event)
        assert result.stdout.strip() == ""


class TestCommitMessageFormat:
    """Tests for commit message prefix validation."""

    def test_blocks_commit_without_prefix(self, run_hook, make_event, tmp_state_dir, tmp_path):
        (tmp_path / "Makefile").touch()
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        _seed_verification_state(tmp_state_dir)
        try:
            event = make_event("Bash", command='git commit -m "add new feature"')
            result = run_hook("git-safety-guard.py", event)
            assert result.parsed is not None
            assert result.parsed["decision"] == "block"
            assert "FORMAT ERROR" in result.parsed["reason"]
        finally:
            os.chdir(old_cwd)

    def test_allows_commit_with_feat_prefix(self, run_hook, make_event, tmp_state_dir, tmp_path):
        (tmp_path / "Makefile").touch()
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        _seed_verification_state(tmp_state_dir)
        try:
            event = make_event("Bash", command='git commit -m "feat: add new feature"')
            result = run_hook("git-safety-guard.py", event)
            assert result.stdout.strip() == ""
        finally:
            os.chdir(old_cwd)

    def test_allows_commit_with_fix_prefix(self, run_hook, make_event, tmp_state_dir, tmp_path):
        (tmp_path / "Makefile").touch()
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        _seed_verification_state(tmp_state_dir)
        try:
            event = make_event("Bash", command='git commit -m "fix: resolve crash on startup"')
            result = run_hook("git-safety-guard.py", event)
            assert result.stdout.strip() == ""
        finally:
            os.chdir(old_cwd)


class TestCommitMessageFileFlag:
    """Tests for -F / --file= commit message extraction."""

    def test_validates_message_from_file(self, run_hook, make_event, tmp_state_dir, tmp_path):
        (tmp_path / "Makefile").touch()
        msg_file = tmp_path / "commit-msg.txt"
        msg_file.write_text("feat: add user authentication\n\nDetailed description here.")
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        _seed_verification_state(tmp_state_dir)
        try:
            event = make_event("Bash", command=f'git commit -F {msg_file}')
            result = run_hook("git-safety-guard.py", event)
            assert result.stdout.strip() == ""
        finally:
            os.chdir(old_cwd)

    def test_blocks_bad_prefix_from_file(self, run_hook, make_event, tmp_state_dir, tmp_path):
        (tmp_path / "Makefile").touch()
        msg_file = tmp_path / "commit-msg.txt"
        msg_file.write_text("add user authentication")
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        _seed_verification_state(tmp_state_dir)
        try:
            event = make_event("Bash", command=f'git commit -F {msg_file}')
            result = run_hook("git-safety-guard.py", event)
            assert result.parsed is not None
            assert result.parsed["decision"] == "block"
            assert "FORMAT ERROR" in result.parsed["reason"]
        finally:
            os.chdir(old_cwd)

    def test_blocks_unreadable_file(self, run_hook, make_event, tmp_state_dir, tmp_path):
        (tmp_path / "Makefile").touch()
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        _seed_verification_state(tmp_state_dir)
        try:
            event = make_event("Bash", command='git commit -F /nonexistent/path.txt')
            result = run_hook("git-safety-guard.py", event)
            assert result.parsed is not None
            assert result.parsed["decision"] == "block"
            assert "UNPARSEABLE" in result.parsed["reason"]
        finally:
            os.chdir(old_cwd)

    def test_validates_double_dash_file(self, run_hook, make_event, tmp_state_dir, tmp_path):
        (tmp_path / "Makefile").touch()
        msg_file = tmp_path / "commit-msg.txt"
        msg_file.write_text("fix: resolve memory leak")
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        _seed_verification_state(tmp_state_dir)
        try:
            event = make_event("Bash", command=f'git commit --file={msg_file}')
            result = run_hook("git-safety-guard.py", event)
            assert result.stdout.strip() == ""
        finally:
            os.chdir(old_cwd)


class TestCommitMessageUnparseable:
    """Tests for block-by-default when message can't be extracted."""

    def test_blocks_commit_with_no_message_flag(self, run_hook, make_event, tmp_state_dir, tmp_path):
        (tmp_path / "Makefile").touch()
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        _seed_verification_state(tmp_state_dir)
        try:
            event = make_event("Bash", command='git commit')
            result = run_hook("git-safety-guard.py", event)
            assert result.parsed is not None
            assert result.parsed["decision"] == "block"
            assert "UNPARSEABLE" in result.parsed["reason"]
        finally:
            os.chdir(old_cwd)

    def test_allows_amend_without_message(self, run_hook, make_event, tmp_state_dir, tmp_path):
        (tmp_path / "Makefile").touch()
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        _seed_verification_state(tmp_state_dir)
        try:
            event = make_event("Bash", command='git commit --amend --no-edit')
            result = run_hook("git-safety-guard.py", event)
            assert result.stdout.strip() == ""
        finally:
            os.chdir(old_cwd)

    def test_bypass_rationalization_in_error(self, run_hook, make_event, tmp_state_dir, tmp_path):
        """Verify the hook bypass rationalization appears in block messages."""
        (tmp_path / "Makefile").touch()
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        _seed_verification_state(tmp_state_dir)
        try:
            event = make_event("Bash", command='git commit -m "add stuff"')
            result = run_hook("git-safety-guard.py", event)
            assert result.parsed is not None
            assert result.parsed["decision"] == "block"
            assert "hook is parsing incorrectly" in result.parsed["reason"].lower()
        finally:
            os.chdir(old_cwd)


class TestExitCodeCheck:
    """Tests that the commit gate checks verification exit codes, not just existence."""

    def test_blocks_commit_when_tests_failed(self, run_hook, make_event, tmp_state_dir, tmp_path):
        """Commit blocked when most recent test run had non-zero exit code."""
        (tmp_path / "Makefile").touch()
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        _seed_verification_state(tmp_state_dir, test_exit_code=1, lint_exit_code=0)
        try:
            event = make_event("Bash", command='git commit -m "feat: add feature"')
            result = run_hook("git-safety-guard.py", event)
            assert result.parsed is not None
            assert result.parsed["decision"] == "block"
            assert "FAILED" in result.parsed["reason"]
            assert "Tests failed" in result.parsed["reason"]
        finally:
            os.chdir(old_cwd)

    def test_blocks_commit_when_lint_failed(self, run_hook, make_event, tmp_state_dir, tmp_path):
        """Commit blocked when most recent lint run had non-zero exit code."""
        (tmp_path / "Makefile").touch()
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        _seed_verification_state(tmp_state_dir, test_exit_code=0, lint_exit_code=1)
        try:
            event = make_event("Bash", command='git commit -m "feat: add feature"')
            result = run_hook("git-safety-guard.py", event)
            assert result.parsed is not None
            assert result.parsed["decision"] == "block"
            assert "FAILED" in result.parsed["reason"]
            assert "Lint failed" in result.parsed["reason"]
        finally:
            os.chdir(old_cwd)

    def test_blocks_commit_when_both_failed(self, run_hook, make_event, tmp_state_dir, tmp_path):
        """Commit blocked when both test and lint runs failed."""
        (tmp_path / "Makefile").touch()
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        _seed_verification_state(tmp_state_dir, test_exit_code=2, lint_exit_code=1)
        try:
            event = make_event("Bash", command='git commit -m "feat: add feature"')
            result = run_hook("git-safety-guard.py", event)
            assert result.parsed is not None
            assert result.parsed["decision"] == "block"
            assert "Tests failed" in result.parsed["reason"]
            assert "Lint failed" in result.parsed["reason"]
        finally:
            os.chdir(old_cwd)

    def test_allows_commit_when_both_passed(self, run_hook, make_event, tmp_state_dir, tmp_path):
        """Commit allowed when both test and lint exit codes are 0."""
        (tmp_path / "Makefile").touch()
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        _seed_verification_state(tmp_state_dir, test_exit_code=0, lint_exit_code=0)
        try:
            event = make_event("Bash", command='git commit -m "feat: add feature"')
            result = run_hook("git-safety-guard.py", event)
            assert result.stdout.strip() == ""
        finally:
            os.chdir(old_cwd)

    def test_allows_commit_when_exit_codes_unknown(self, run_hook, make_event, tmp_state_dir, tmp_path):
        """Commit allowed when exit codes are None (unknown — PreToolUse fallback)."""
        (tmp_path / "Makefile").touch()
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        _seed_verification_state(tmp_state_dir, test_exit_code=None, lint_exit_code=None)
        try:
            event = make_event("Bash", command='git commit -m "feat: add feature"')
            result = run_hook("git-safety-guard.py", event)
            assert result.stdout.strip() == ""
        finally:
            os.chdir(old_cwd)

    def test_pytest_exit_code_5_treated_as_passing(self, run_hook, make_event, tmp_state_dir, tmp_path):
        """Exit code 5 (pytest no tests collected) should not block commits."""
        (tmp_path / "Makefile").touch()
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        _seed_verification_state(tmp_state_dir, test_exit_code=5, lint_exit_code=0)
        try:
            event = make_event("Bash", command='git commit -m "feat: add feature"')
            result = run_hook("git-safety-guard.py", event)
            assert result.stdout.strip() == ""
        finally:
            os.chdir(old_cwd)

    def test_pre_existing_failure_rationalization_in_message(self, run_hook, make_event, tmp_state_dir, tmp_path):
        """Block message includes named rationalization about pre-existing failures."""
        (tmp_path / "Makefile").touch()
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        _seed_verification_state(tmp_state_dir, test_exit_code=1, lint_exit_code=0)
        try:
            event = make_event("Bash", command='git commit -m "feat: add feature"')
            result = run_hook("git-safety-guard.py", event)
            assert result.parsed is not None
            assert "pre-existing failure" in result.parsed["reason"].lower()
        finally:
            os.chdir(old_cwd)
