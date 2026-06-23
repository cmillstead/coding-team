"""Tests for git-safety-guard.py hook."""

import hashlib
import json
import os
import subprocess
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


# ---------------------------------------------------------------------------
# Helpers for submodule-pointer (gitlink) tests
# ---------------------------------------------------------------------------

def _git(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    """Run a git command in the given directory."""
    return subprocess.run(
        ["git"] + args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=check,
        env={**os.environ, "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "t@test.com",
             "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "t@test.com"},
    )


def _make_repo_with_commit(path: Path, branch: str = "feat/test") -> None:
    """Initialise a git repo at *path* with a single commit on *branch*.

    Uses a non-protected branch name by default so the branch guard does not
    fire during tests that focus on the docs-only / pointer-only exemptions.
    """
    _git(["init", "-b", branch, str(path)], cwd=path.parent)
    (path / "README.md").write_text("# inner\n")
    _git(["add", "README.md"], cwd=path)
    _git(["commit", "-m", "chore: initial"], cwd=path)


def _stage_gitlink(outer: Path, inner: Path) -> None:
    """Stage the inner repo as a gitlink in the outer repo.

    git treats an un-tracked directory that is itself a git repo as a
    gitlink (mode 160000) when added — exactly what a submodule pointer is.
    """
    _git(["add", str(inner)], cwd=outer)


def _verify_gitlink_staged(outer: Path, inner: Path) -> bool:
    """Return True if the inner path is staged as mode 160000 in the outer repo."""
    result = _git(["diff", "--cached", "--raw"], cwd=outer)
    rel = inner.relative_to(outer)
    for line in result.stdout.splitlines():
        # Format: :old-mode new-mode old-sha new-sha status\tpath
        if str(rel) in line and "160000" in line:
            return True
    return False


class TestPointerOnlyCommit:
    """Tests for is_pointer_only_commit exemption (submodule gitlink-only commits)."""

    def test_pointer_only_returns_true_and_hook_skips_checklist(
        self, run_hook, make_event, tmp_state_dir, tmp_path
    ):
        """Staging only a gitlink change → hook allows commit without checklist."""
        # Arrange: outer repo with infrastructure already committed, inner repo staged
        # as a new gitlink entry (mode 160000 addition).
        outer = tmp_path / "outer"
        inner = outer / "sub"
        outer.mkdir()

        # Bootstrap the outer repo with Makefile (so infrastructure check fires).
        _git(["init", "-b", "feat/test", str(outer)], cwd=outer.parent)
        (outer / "Makefile").touch()
        (outer / "README.md").write_text("# outer\n")
        _git(["add", "Makefile", "README.md"], cwd=outer)
        _git(["commit", "-m", "chore: initial"], cwd=outer)

        # Create and bootstrap the inner repo.
        inner.mkdir()
        _make_repo_with_commit(inner)

        # Stage the inner repo as a gitlink (new addition, mode 160000).
        _stage_gitlink(outer, inner)

        assert _verify_gitlink_staged(outer, inner), (
            "Setup failed: inner repo not staged as mode 160000 in outer repo"
        )

        old_cwd = os.getcwd()
        os.chdir(str(outer))
        # Do NOT seed verification state — checklist would block if it fires.
        try:
            command = f'cd {outer} && git commit -m "chore: bump sub pointer"'
            event = make_event("Bash", command=command)
            result = run_hook("git-safety-guard.py", event)
            # Hook should allow (no block output) because it's pointer-only.
            assert result.stdout.strip() == "", (
                f"Expected silent allow for pointer-only commit, got: {result.stdout!r}"
            )
        finally:
            os.chdir(old_cwd)

    def test_mixed_gitlink_and_py_file_is_not_exempt(
        self, run_hook, make_event, tmp_state_dir, tmp_path
    ):
        """Staging a gitlink plus a .py file → not pointer-only → checklist applies."""
        # Arrange: outer repo with infrastructure committed first, then both a
        # gitlink and a .py file staged together.
        outer = tmp_path / "outer"
        inner = outer / "sub"
        outer.mkdir()

        # Bootstrap outer with infrastructure only (no sub yet).
        _git(["init", "-b", "feat/test", str(outer)], cwd=outer.parent)
        (outer / "Makefile").touch()
        _git(["add", "Makefile"], cwd=outer)
        _git(["commit", "-m", "chore: initial"], cwd=outer)

        inner.mkdir()
        _make_repo_with_commit(inner)

        # Stage both the gitlink and a .py file

        old_cwd = os.getcwd()
        os.chdir(str(outer))
        # No verification state → checklist fires and blocks.
        try:
            command = f'cd {outer} && git commit -m "feat: add module"'
            event = make_event("Bash", command=command)
            result = run_hook("git-safety-guard.py", event)
            # Should be blocked by the verification checklist (not pointer-only).
            assert result.parsed is not None, (
                f"Expected block for mixed commit, got empty stdout: {result.stderr!r}"
            )
            assert result.parsed["decision"] == "block"
        finally:
            os.chdir(old_cwd)

    def test_docs_only_commit_still_exempt(
        self, run_hook, make_event, tmp_state_dir, tmp_path
    ):
        """Regression: a docs-only .md commit remains exempt after pointer logic added."""
        # Arrange: repo with infrastructure committed, then only a .md file staged.
        outer = tmp_path / "outer"
        outer.mkdir()

        _git(["init", "-b", "feat/test", str(outer)], cwd=outer.parent)
        (outer / "Makefile").touch()
        _git(["add", "Makefile"], cwd=outer)
        _git(["commit", "-m", "chore: initial"], cwd=outer)

        (outer / "NOTES.md").write_text("# notes\n")
        _git(["add", "NOTES.md"], cwd=outer)

        old_cwd = os.getcwd()
        os.chdir(str(outer))
        # No verification state — exemption must fire before checklist.
        try:
            command = f'cd {outer} && git commit -m "docs: update notes"'
            event = make_event("Bash", command=command)
            result = run_hook("git-safety-guard.py", event)
            assert result.stdout.strip() == "", (
                f"Expected silent allow for docs-only commit, got: {result.stdout!r}"
            )
        finally:
            os.chdir(old_cwd)

    def test_empty_staged_is_not_pointer_only(
        self, run_hook, make_event, tmp_state_dir, tmp_path
    ):
        """Empty staged set → is_pointer_only_commit returns False (fail-safe)."""
        # Arrange: repo with infrastructure committed, nothing else staged.
        outer = tmp_path / "outer"
        outer.mkdir()

        _git(["init", "-b", "feat/test", str(outer)], cwd=outer.parent)
        (outer / "Makefile").touch()
        _git(["add", "Makefile"], cwd=outer)
        _git(["commit", "-m", "chore: initial"], cwd=outer)
        # Nothing staged now.

        old_cwd = os.getcwd()
        os.chdir(str(outer))
        # No verification state — if fail-safe fires correctly, checklist blocks.
        try:
            command = f'cd {outer} && git commit -m "chore: empty"'
            event = make_event("Bash", command=command)
            result = run_hook("git-safety-guard.py", event)
            # Should be blocked (by checklist, since nothing is staged and both
            # pointer-only and docs-only must return False for empty staged set).
            assert result.parsed is not None, (
                f"Expected block for empty staged commit, got: {result.stderr!r}"
            )
            assert result.parsed["decision"] == "block"
        finally:
            os.chdir(old_cwd)


# ---------------------------------------------------------------------------
# Helpers for branch-check chaining tests
# ---------------------------------------------------------------------------

def _make_repo_on_branch(path: Path, branch: str = "main") -> None:
    """Initialise a git repo at *path* with a single commit on *branch*."""
    _git(["init", "-b", branch, str(path)], cwd=path.parent)
    (path / "README.md").write_text(f"# repo on {branch}\n")
    _git(["add", "README.md"], cwd=path)
    _git(["commit", "-m", "chore: initial"], cwd=path)


class TestBranchCheckChainingBypass:
    """Tests for the chained-command branch-check bypass bug.

    Bug: git_subcmd = extract_git_command(command) returns the FIRST git
    subcommand.  For `git add f && git commit -m x`, git_subcmd is 'add',
    so the condition `git_subcmd in ('commit', 'push', 'merge')` is False
    and the branch check is skipped — a direct commit to main slips through.

    Fix: replace the fragile first-token condition with is_commit_push_or_merge(command),
    which uses a regex to find commit/push/merge *anywhere* in the command.
    """

    def test_chained_add_then_commit_blocked_on_main(self, run_hook, make_event, tmp_path):
        """BUG REPRO: chained `git add f && git commit -m x` on main → BLOCKED.

        This test must be RED before the fix (the bug lets the commit through).
        """
        repo = tmp_path / "repo"
        repo.mkdir()
        _make_repo_on_branch(repo, branch="main")

        # Stage a new file for the chained command to commit.
        (repo / "new_file.py").write_text("x = 1\n")

        old_cwd = os.getcwd()
        os.chdir(str(repo))
        try:
            command = f'cd {repo} && git add new_file.py && git commit -m "feat: add x"'
            event = make_event("Bash", command=command)
            result = run_hook("git-safety-guard.py", event)
            assert result.parsed is not None, (
                f"Expected BLOCK for chained commit on main, got silent allow. "
                f"stderr: {result.stderr!r}"
            )
            assert result.parsed["decision"] == "block"
            assert "feature branch" in result.parsed["reason"].lower()
        finally:
            os.chdir(old_cwd)

    def test_plain_commit_on_main_still_blocked(self, run_hook, make_event, tmp_path):
        """Regression: plain `git commit -m x` on main → still BLOCKED after fix."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _make_repo_on_branch(repo, branch="main")

        old_cwd = os.getcwd()
        os.chdir(str(repo))
        try:
            command = f'cd {repo} && git commit -m "feat: plain commit"'
            event = make_event("Bash", command=command)
            result = run_hook("git-safety-guard.py", event)
            assert result.parsed is not None, (
                f"Expected BLOCK for plain commit on main, got: {result.stdout!r}"
            )
            assert result.parsed["decision"] == "block"
            assert "feature branch" in result.parsed["reason"].lower()
        finally:
            os.chdir(old_cwd)

    def test_chained_add_then_commit_allowed_on_feature_branch(
        self, run_hook, make_event, tmp_path
    ):
        """Chained `git add f && git commit -m x` on a feature branch → NOT blocked."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _make_repo_on_branch(repo, branch="feature/x")

        (repo / "new_file.py").write_text("x = 1\n")

        old_cwd = os.getcwd()
        os.chdir(str(repo))
        try:
            command = f'cd {repo} && git add new_file.py && git commit -m "feat: add x"'
            event = make_event("Bash", command=command)
            result = run_hook("git-safety-guard.py", event)
            # The branch check must NOT fire (we're on a feature branch).
            # The verification checklist may fire (no infra in repo), but
            # that's a different block — we verify it's not a branch-guard block.
            if result.parsed is not None and result.parsed.get("decision") == "block":
                reason = result.parsed["reason"]
                assert "feature branch" not in reason.lower(), (
                    f"Branch guard incorrectly fired on feature branch: {reason!r}"
                )
        finally:
            os.chdir(old_cwd)

    def test_git_merge_on_main_blocked(self, run_hook, make_event, tmp_path):
        """git merge on main → BLOCKED (verifies merge is covered by the fix)."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _make_repo_on_branch(repo, branch="main")

        old_cwd = os.getcwd()
        os.chdir(str(repo))
        try:
            command = f'cd {repo} && git merge feature/x'
            event = make_event("Bash", command=command)
            result = run_hook("git-safety-guard.py", event)
            assert result.parsed is not None, (
                f"Expected BLOCK for merge on main, got: {result.stdout!r}"
            )
            assert result.parsed["decision"] == "block"
            assert "feature branch" in result.parsed["reason"].lower()
        finally:
            os.chdir(old_cwd)

    def test_delete_only_push_on_main_not_blocked(self, run_hook, make_event, tmp_path):
        """Delete-only push on main → NOT blocked (is_delete_only_push exemption preserved)."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _make_repo_on_branch(repo, branch="main")

        old_cwd = os.getcwd()
        os.chdir(str(repo))
        try:
            command = f'cd {repo} && git push origin :old-branch'
            event = make_event("Bash", command=command)
            result = run_hook("git-safety-guard.py", event)
            # A delete-only push must NOT be blocked by the branch guard.
            if result.parsed is not None and result.parsed.get("decision") == "block":
                reason = result.parsed["reason"]
                assert "feature branch" not in reason.lower(), (
                    f"Branch guard incorrectly blocked delete-only push: {reason!r}"
                )
        finally:
            os.chdir(old_cwd)


# ---------------------------------------------------------------------------
# Tests for has_project_infrastructure with script-less package.json fix
# ---------------------------------------------------------------------------

class TestHasProjectInfrastructurePackageJson:
    """Unit tests for has_project_infrastructure() with package.json refinement.

    A script-less package.json (scripts: {} or no test/lint keys) must NOT
    count as infrastructure — it provides no runnable verification command
    and would make the verification checklist permanently un-satisfiable.
    """

    def _infra(self, tmp_path: Path) -> bool:
        """Load and call has_project_infrastructure from the hook file directly.

        Uses spec_from_file_location because the filename contains a hyphen and
        cannot be imported as a regular Python module name.  Reloads each call
        so post-fix state is always reflected.
        """
        import importlib.util
        hook_path = Path(__file__).parent.parent / "git-safety-guard.py"
        spec = importlib.util.spec_from_file_location("git_safety_guard", str(hook_path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.has_project_infrastructure(str(tmp_path))

    def test_scriptless_package_json_is_not_infra(self, tmp_path):
        """(a) BUG REPRO: package.json with empty scripts → not infrastructure.

        RED before the fix (currently returns True unconditionally).
        """
        (tmp_path / "package.json").write_text(json.dumps({"scripts": {}}))
        assert self._infra(tmp_path) is False

    def test_package_json_with_test_script_is_infra(self, tmp_path):
        """(b) package.json with a 'test' script → infrastructure."""
        (tmp_path / "package.json").write_text(json.dumps({"scripts": {"test": "jest"}}))
        assert self._infra(tmp_path) is True

    def test_package_json_with_lint_script_is_infra(self, tmp_path):
        """(c) package.json with a 'lint' script → infrastructure."""
        (tmp_path / "package.json").write_text(json.dumps({"scripts": {"lint": "eslint ."}}))
        assert self._infra(tmp_path) is True

    def test_package_json_build_only_is_not_infra(self, tmp_path):
        """(d) BUG REPRO: package.json with only a 'build' script → not infrastructure.

        RED before the fix (currently returns True unconditionally).
        """
        (tmp_path / "package.json").write_text(json.dumps({"scripts": {"build": "webpack"}}))
        assert self._infra(tmp_path) is False

    def test_scriptless_package_json_plus_pyproject_is_infra(self, tmp_path):
        """(e) Script-less package.json + pyproject.toml → True (other marker counts)."""
        (tmp_path / "package.json").write_text(json.dumps({"scripts": {}}))
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\n")
        assert self._infra(tmp_path) is True

    def test_malformed_package_json_is_infra_fail_safe(self, tmp_path):
        """(f) Malformed/truncated package.json → True (fail-safe: assume verification needed)."""
        (tmp_path / "package.json").write_text("{ not json")
        assert self._infra(tmp_path) is True

    def test_empty_dir_is_not_infra(self, tmp_path):
        """(g) Empty dir with no markers → False (docs-only behavior preserved)."""
        assert self._infra(tmp_path) is False


class TestLongCommandVerificationTracking:
    """The full command (not command[:100]) must be stored so (a) the commit gate's
    test/lint regex matches a verify token even past char 100, and (b) the PreToolUse
    dedup distinguishes commands that differ only in their tail."""

    def _state_path(self, session_id: str) -> Path:
        session_hash = hashlib.sha256(session_id.encode()).hexdigest()[:12]
        return Path(f"/tmp/claude-verification-{session_hash}.json")

    def test_full_command_stored_untruncated(self, run_hook, make_event, tmp_state_dir):
        cmd = "cd /repo && echo " + ("x" * 110) + " && cargo test --workspace"
        assert "cargo test" not in cmd[:100]
        run_hook("git-safety-guard.py",
                 make_event("Bash", command=cmd, tool_result={"exit_code": 0}))
        st = json.loads(self._state_path(tmp_state_dir).read_text())
        stored = st["verifications"][-1]["command"]
        assert stored == cmd
        assert "cargo test" in stored

    def test_dedup_distinguishes_commands_differing_only_in_tail(self, run_hook, make_event, tmp_state_dir):
        pad = "x" * 90
        cmd_a = f"cd /repo && echo {pad} && cargo test --workspace --all-features"
        cmd_b = f"cd /repo && echo {pad} && cargo test --workspace --lib"
        assert cmd_a[:100] == cmd_b[:100]
        run_hook("git-safety-guard.py", make_event("Bash", command=cmd_a))
        run_hook("git-safety-guard.py", make_event("Bash", command=cmd_b))
        st = json.loads(self._state_path(tmp_state_dir).read_text())
        stored = [v["command"] for v in st["verifications"]]
        assert cmd_a in stored and cmd_b in stored


# ---------------------------------------------------------------------------
# Tests for check_codex_digest_sync (inline build-digest.py --check gate)
# ---------------------------------------------------------------------------

def _load_hook_module():
    """Import git-safety-guard.py as a module (hyphenated filename)."""
    import importlib.util
    hook_path = Path(__file__).parent.parent / "git-safety-guard.py"
    spec = importlib.util.spec_from_file_location("git_safety_guard", str(hook_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Real-shaped entry: a single '**Design default:**' line is required by build-digest.py.
_ENTRY_P1 = (
    "# P1\n\n"
    "| ID | Pattern | Check |\n"
    "|----|---------|-------|\n"
    "| P1 | Phantom symbol | Grep for every named symbol. |\n\n"
    "**Design default:** Verify every symbol the plan names exists before writing the plan.\n"
)

_ENTRY_C1 = (
    "# C1\n\n"
    "| ID | Pattern | Check |\n"
    "|----|---------|-------|\n"
    "| C1 | Single-gate path trust | Classify path-shaped fields into tiers. |\n\n"
    "**Design default:** Classify a path-shaped field as identifier / fs-path / repo-relative.\n"
)


def _build_codex_repo(root: Path) -> Path:
    """Create a git repo containing the REAL build-digest.py + real-shaped entries.

    Copies the actual generator script so check_codex_digest_sync runs the real
    code (no mocks). Returns the repo root.
    """
    so = root / "skills" / "second-opinion"
    entries = so / "codex-learnings.d"
    scripts = so / "scripts"
    entries.mkdir(parents=True)
    scripts.mkdir(parents=True)

    # Copy the REAL generator script.
    real_script = Path(__file__).parent.parent.parent / "skills" / "second-opinion" / "scripts" / "build-digest.py"
    (scripts / "build-digest.py").write_text(real_script.read_text(encoding="utf-8"), encoding="utf-8")

    # Write real-shaped entries.
    (entries / "p01-phantom-symbol.md").write_text(_ENTRY_P1, encoding="utf-8")
    (entries / "c01-single-gate-path-trust.md").write_text(_ENTRY_C1, encoding="utf-8")

    # Give the repo verification infrastructure (irrelevant to the digest gate
    # but keeps the fixture realistic).
    (root / "Makefile").touch()

    _git(["init", "-b", "feat/test", str(root)], cwd=root.parent)
    _git(["add", "."], cwd=root)
    _git(["commit", "-m", "chore: initial codex tree"], cwd=root)
    return root


def _regenerate_digest(root: Path) -> None:
    """Run the real build-digest.py (no --check) to write an in-sync digest."""
    script = root / "skills" / "second-opinion" / "scripts" / "build-digest.py"
    subprocess.run(["python3", str(script)], check=True, capture_output=True, text=True)


class TestCodexDigestSyncGate:
    """check_codex_digest_sync runs the REAL build-digest.py --check inline."""

    def test_fires_when_entry_edited_and_digest_stale(self, tmp_path):
        """(a) LOAD-BEARING: edited entry + stale digest → returns a block message."""
        mod = _load_hook_module()
        repo = _build_codex_repo(tmp_path / "repo")

        # Generate an in-sync digest, commit it, then EDIT an entry's Design
        # default WITHOUT regenerating the digest → digest is now stale.
        _regenerate_digest(repo)
        _git(["add", "skills/second-opinion/codex-learnings-digest.md"], cwd=repo)
        _git(["commit", "-m", "chore: add digest"], cwd=repo)

        entry = repo / "skills" / "second-opinion" / "codex-learnings.d" / "p01-phantom-symbol.md"
        entry.write_text(_ENTRY_P1.replace(
            "**Design default:** Verify every symbol the plan names exists before writing the plan.\n",
            "**Design default:** A COMPLETELY DIFFERENT default that the stale digest does not reflect.\n",
        ), encoding="utf-8")
        _git(["add", "skills/second-opinion/codex-learnings.d/p01-phantom-symbol.md"], cwd=repo)

        command = f'cd {repo} && git commit -m "fix: tweak p01 default"'
        block = mod.check_codex_digest_sync(command, str(repo))

        # The gate FIRES: returns a non-None block message naming the fix.
        assert block is not None, "Gate must FIRE (return a block message) for a stale digest"
        assert "CODEX DIGEST STALE" in block
        assert "run build-digest.py to regenerate the digest, then re-commit" in block
        assert "the entry change is trivial" in block

    def test_returns_none_when_digest_in_sync(self, tmp_path):
        """(b) entry committed with the digest correctly regenerated → None (allowed)."""
        mod = _load_hook_module()
        repo = _build_codex_repo(tmp_path / "repo")

        # Edit an entry AND regenerate the digest so they are in sync, stage both.
        entry = repo / "skills" / "second-opinion" / "codex-learnings.d" / "p01-phantom-symbol.md"
        entry.write_text(_ENTRY_P1.replace(
            "before writing the plan.",
            "before writing the plan, every time.",
        ), encoding="utf-8")
        _regenerate_digest(repo)
        _git(["add", "skills/second-opinion/codex-learnings.d/p01-phantom-symbol.md"], cwd=repo)
        _git(["add", "skills/second-opinion/codex-learnings-digest.md"], cwd=repo)

        command = f'cd {repo} && git commit -m "fix: tweak p01 and regen"'
        assert mod.check_codex_digest_sync(command, str(repo)) is None

    def test_returns_none_for_unrelated_commit(self, tmp_path):
        """(c) commit touching only non-codex files → None and --check NOT run."""
        mod = _load_hook_module()
        repo = _build_codex_repo(tmp_path / "repo")

        # Stage an unrelated file outside the codex digest-input set.
        (repo / "unrelated.py").write_text("x = 1\n")
        _git(["add", "unrelated.py"], cwd=repo)

        command = f'cd {repo} && git commit -m "feat: unrelated change"'
        assert mod.check_codex_digest_sync(command, str(repo)) is None

    def test_returns_none_when_script_missing(self, tmp_path):
        """(d) fail-open: codex entries staged but generator script absent → None."""
        mod = _load_hook_module()
        repo = _build_codex_repo(tmp_path / "repo")

        # Remove the generator script, then stage a codex entry edit.
        script = repo / "skills" / "second-opinion" / "scripts" / "build-digest.py"
        script.unlink()
        _git(["add", "skills/second-opinion/scripts/build-digest.py"], cwd=repo)

        entry = repo / "skills" / "second-opinion" / "codex-learnings.d" / "c01-single-gate-path-trust.md"
        entry.write_text(_ENTRY_C1.replace("repo-relative.", "repo-relative; always."), encoding="utf-8")
        _git(["add", "skills/second-opinion/codex-learnings.d/c01-single-gate-path-trust.md"], cwd=repo)

        command = f'cd {repo} && git commit -m "fix: edit c01"'
        assert mod.check_codex_digest_sync(command, str(repo)) is None

    def test_returns_none_for_push_command(self, tmp_path):
        """A push (not a commit) is out of scope → None even if codex paths involved."""
        mod = _load_hook_module()
        repo = _build_codex_repo(tmp_path / "repo")
        command = f'cd {repo} && git push origin feat/test'
        assert mod.check_codex_digest_sync(command, str(repo)) is None

    def test_fails_open_when_generator_crashes(self, tmp_path):
        """FIX 1: a REAL crashing generator (exit 1) → None (fail OPEN), never a block.

        Python exits 1 on an uncaught exception too. The gate must distinguish a
        genuine crash from a cleanly-determined stale digest (exit 3): a broken
        generator while editing the script must NOT block the commit.
        """
        mod = _load_hook_module()
        repo = _build_codex_repo(tmp_path / "repo")

        # Replace the copied generator with one that genuinely exits 1 (real
        # failing subprocess, not a mock) and STAGE it, so the materialized
        # index check (plain commit) invokes this crashing version. Also stage
        # an entry edit so the gate decides to run --check.
        script = repo / "skills" / "second-opinion" / "scripts" / "build-digest.py"
        script.write_text("import sys\nsys.exit(1)\n", encoding="utf-8")
        _git(["add", "skills/second-opinion/scripts/build-digest.py"], cwd=repo)

        entry = repo / "skills" / "second-opinion" / "codex-learnings.d" / "p01-phantom-symbol.md"
        entry.write_text(_ENTRY_P1.replace(
            "before writing the plan.",
            "before writing the plan, always.",
        ), encoding="utf-8")
        _git(["add", "skills/second-opinion/codex-learnings.d/p01-phantom-symbol.md"], cwd=repo)

        command = f'cd {repo} && git commit -m "fix: edit p01"'
        # rc==1 (crash) must NOT block: fail open.
        assert mod.check_codex_digest_sync(command, str(repo)) is None

    def test_fires_when_only_generator_script_staged_and_digest_stale(self, tmp_path):
        """FIX 2: staging ONLY the generator script with a stale digest → gate FIRES.

        A change to build-digest.py (sort/extraction/format logic) can silently
        change the rendering, so it is itself a digest input that must trigger
        --check.
        """
        mod = _load_hook_module()
        repo = _build_codex_repo(tmp_path / "repo")

        # Commit an in-sync digest first.
        _regenerate_digest(repo)
        _git(["add", "skills/second-opinion/codex-learnings-digest.md"], cwd=repo)
        _git(["commit", "-m", "chore: add digest"], cwd=repo)

        # Edit the generator so the rendering would change (append a trailing
        # marker line to every rendered digest) WITHOUT regenerating the digest,
        # then stage ONLY the script. The committed digest is now stale.
        script = repo / "skills" / "second-opinion" / "scripts" / "build-digest.py"
        src = script.read_text(encoding="utf-8")
        src = src.replace(
            'text = "\\n".join(clean_lines) + "\\n"',
            'text = "\\n".join(clean_lines) + "\\n<!-- v2 -->\\n"',
            1,
        )
        script.write_text(src, encoding="utf-8")
        _git(["add", "skills/second-opinion/scripts/build-digest.py"], cwd=repo)

        command = f'cd {repo} && git commit -m "feat: change digest format"'
        block = mod.check_codex_digest_sync(command, str(repo))

        assert block is not None, "Gate must FIRE when only the generator script is staged and the digest is stale"
        assert "CODEX DIGEST STALE" in block

    def test_commit_dash_am_bypass_is_fixed(self, tmp_path):
        """FIX A: `git commit -am` with a stale tracked entry (NOTHING staged) FIRES.

        `git commit -a/-am` commits tracked modifications not in the index, so
        `git diff --cached` is empty. The gate must consult the tracked-modified
        set so the stale-digest protection is not silently bypassed. Before this
        fix the gate returned None.
        """
        mod = _load_hook_module()
        repo = _build_codex_repo(tmp_path / "repo")

        # Commit an in-sync digest, then modify a tracked entry WITHOUT staging
        # it and WITHOUT regenerating the digest → digest is stale, index empty.
        _regenerate_digest(repo)
        _git(["add", "skills/second-opinion/codex-learnings-digest.md"], cwd=repo)
        _git(["commit", "-m", "chore: add digest"], cwd=repo)

        entry = repo / "skills" / "second-opinion" / "codex-learnings.d" / "p01-phantom-symbol.md"
        entry.write_text(_ENTRY_P1.replace(
            "**Design default:** Verify every symbol the plan names exists before writing the plan.\n",
            "**Design default:** A DIFFERENT default the stale digest does not reflect.\n",
        ), encoding="utf-8")

        # Sanity: nothing is staged.
        assert _git(["diff", "--cached", "--name-only"], cwd=repo).stdout.strip() == ""

        command = f'cd {repo} && git commit -am "fix: tweak p01"'
        block = mod.check_codex_digest_sync(command, str(repo))

        assert block is not None, "git commit -am must FIRE the gate for a stale tracked entry"
        assert "CODEX DIGEST STALE" in block

    def test_commit_dash_am_in_sync_returns_none(self, tmp_path):
        """FIX A: `git commit -am` with the working tree in sync → None (allowed)."""
        mod = _load_hook_module()
        repo = _build_codex_repo(tmp_path / "repo")

        # Commit an in-sync digest so BOTH the entry and the digest are TRACKED
        # (a -a commit only captures tracked modifications; the digest must be
        # tracked to be part of the to-be-committed tree).
        _regenerate_digest(repo)
        _git(["add", "skills/second-opinion/codex-learnings-digest.md"], cwd=repo)
        _git(["commit", "-m", "chore: add digest"], cwd=repo)

        # Edit the tracked entry, regenerate the digest so the WORKING TREE is in
        # sync, stage NOTHING (a -a commit captures tracked modifications).
        entry = repo / "skills" / "second-opinion" / "codex-learnings.d" / "p01-phantom-symbol.md"
        entry.write_text(_ENTRY_P1.replace(
            "before writing the plan.",
            "before writing the plan, consistently.",
        ), encoding="utf-8")
        _regenerate_digest(repo)

        assert _git(["diff", "--cached", "--name-only"], cwd=repo).stdout.strip() == ""

        command = f'cd {repo} && git commit -am "fix: tweak p01 and regen"'
        assert mod.check_codex_digest_sync(command, str(repo)) is None

    def test_plain_commit_fires_on_staged_drift(self, tmp_path):
        """Plain commit with a staged entry but a STALE digest → FIRES.

        Stage an edited entry but NOT a regenerated digest, so the tracked
        working-tree digest is stale relative to the edited entry. The
        grammar-free working-tree check must FIRE.
        """
        mod = _load_hook_module()
        repo = _build_codex_repo(tmp_path / "repo")

        # Commit an in-sync digest first.
        _regenerate_digest(repo)
        _git(["add", "skills/second-opinion/codex-learnings-digest.md"], cwd=repo)
        _git(["commit", "-m", "chore: add digest"], cwd=repo)

        # Stage an entry edit but NOT a regenerated digest → staged drift.
        entry = repo / "skills" / "second-opinion" / "codex-learnings.d" / "p01-phantom-symbol.md"
        entry.write_text(_ENTRY_P1.replace(
            "**Design default:** Verify every symbol the plan names exists before writing the plan.\n",
            "**Design default:** A staged-but-unreflected default.\n",
        ), encoding="utf-8")
        _git(["add", "skills/second-opinion/codex-learnings.d/p01-phantom-symbol.md"], cwd=repo)

        command = f'cd {repo} && git commit -m "fix: tweak p01"'
        block = mod.check_codex_digest_sync(command, str(repo))

        assert block is not None, "Plain commit must FIRE when the staged digest is stale vs the staged entry"
        assert "CODEX DIGEST STALE" in block

    def test_commit_all_excludes_untracked_draft_entry(self, tmp_path):
        """FIX 2: `-a` commit (tracked entry in sync) with an UNTRACKED draft → None.

        `git commit -a` commits tracked modifications but NOT untracked files.
        An untracked draft entry under codex-learnings.d must therefore be
        EXCLUDED from the materialized tree and never cause a false block. A
        working-tree-direct check would wrongly include the draft and could
        block; the materialized (ls-files) check excludes it.
        """
        mod = _load_hook_module()
        repo = _build_codex_repo(tmp_path / "repo")

        # Working tree is in sync: regenerate the digest for the tracked entries.
        _regenerate_digest(repo)
        _git(["add", "skills/second-opinion/codex-learnings-digest.md"], cwd=repo)
        _git(["commit", "-m", "chore: add digest"], cwd=repo)

        # Edit a TRACKED entry and regenerate so the tracked set stays in sync;
        # stage nothing (a -a commit captures tracked modifications).
        entry = repo / "skills" / "second-opinion" / "codex-learnings.d" / "p01-phantom-symbol.md"
        entry.write_text(_ENTRY_P1.replace(
            "before writing the plan.",
            "before writing the plan, reliably.",
        ), encoding="utf-8")
        _regenerate_digest(repo)

        # Drop an UNTRACKED draft entry whose Design default is NOT in the digest.
        draft = repo / "skills" / "second-opinion" / "codex-learnings.d" / "20260620-120000-ab12-draft.md"
        draft.write_text(
            "# C2\n\n"
            "| ID | Pattern | Check |\n"
            "|----|---------|------|\n"
            "| C2 | Draft | Draft check |\n\n"
            "**Design default:** An UNTRACKED draft default not yet in the digest.\n",
            encoding="utf-8",
        )
        # Sanity: the draft is untracked.
        status = _git(["status", "--porcelain", "--", str(draft)], cwd=repo).stdout
        assert status.startswith("??"), status

        command = f'cd {repo} && git commit -am "fix: tweak p01"'
        # The untracked draft is NOT part of the -a commit → no false block.
        assert mod.check_codex_digest_sync(command, str(repo)) is None

    def test_commit_all_fires_when_working_tree_edit_stales_digest(self, tmp_path):
        """FIX 2: `-a` commit of a tracked entry whose working-tree edit stales the digest → FIRES.

        A `-a` commit captures tracked working-tree modifications. Editing a
        tracked entry WITHOUT regenerating the digest makes the to-be-committed
        digest stale; the materialized working-tree check must FIRE.
        """
        mod = _load_hook_module()
        repo = _build_codex_repo(tmp_path / "repo")

        # In-sync digest committed.
        _regenerate_digest(repo)
        _git(["add", "skills/second-opinion/codex-learnings-digest.md"], cwd=repo)
        _git(["commit", "-m", "chore: add digest"], cwd=repo)

        # Edit a tracked entry in the working tree WITHOUT regenerating the digest
        # and stage NOTHING (a -a commit captures the tracked modification).
        entry = repo / "skills" / "second-opinion" / "codex-learnings.d" / "p01-phantom-symbol.md"
        entry.write_text(_ENTRY_P1.replace(
            "**Design default:** Verify every symbol the plan names exists before writing the plan.\n",
            "**Design default:** A working-tree edit the stale digest does not reflect.\n",
        ), encoding="utf-8")
        assert _git(["diff", "--cached", "--name-only"], cwd=repo).stdout.strip() == ""

        command = f'cd {repo} && git commit -am "fix: tweak p01"'
        block = mod.check_codex_digest_sync(command, str(repo))

        assert block is not None, "-a commit must FIRE when a tracked working-tree edit stales the digest"
        assert "CODEX DIGEST STALE" in block

    def test_tracked_modified_unstaged_entry_fires(self, tmp_path):
        """Tracked entry modified UNSTAGED (no staging) with a stale digest → FIRES.

        This is the `git commit -a` case, now covered WITHOUT any flag parsing:
        the trigger set is the union of staged AND tracked-unstaged-modified
        files, and the check runs against the tracked working tree.
        """
        mod = _load_hook_module()
        repo = _build_codex_repo(tmp_path / "repo")

        # Commit an in-sync digest, then modify a tracked entry WITHOUT staging
        # it and WITHOUT regenerating the digest → digest stale, index empty.
        _regenerate_digest(repo)
        _git(["add", "skills/second-opinion/codex-learnings-digest.md"], cwd=repo)
        _git(["commit", "-m", "chore: add digest"], cwd=repo)

        entry = repo / "skills" / "second-opinion" / "codex-learnings.d" / "p01-phantom-symbol.md"
        entry.write_text(_ENTRY_P1.replace(
            "**Design default:** Verify every symbol the plan names exists before writing the plan.\n",
            "**Design default:** A DIFFERENT default the stale digest does not reflect.\n",
        ), encoding="utf-8")

        # Sanity: nothing is staged — the modification is tracked-unstaged only.
        assert _git(["diff", "--cached", "--name-only"], cwd=repo).stdout.strip() == ""

        # A plain `git commit` here would normally be empty, but the gate keys off
        # the union set; the tracked-modified entry triggers the check.
        command = f'cd {repo} && git commit -m "fix: tweak p01"'
        block = mod.check_codex_digest_sync(command, str(repo))

        assert block is not None, "tracked-modified-unstaged stale entry must FIRE the gate"
        assert "CODEX DIGEST STALE" in block

    def test_untracked_draft_entry_excluded(self, tmp_path):
        """Tracked entry in sync + an UNTRACKED draft entry present → None.

        `git ls-files` lists tracked paths only, so an untracked draft under the
        codex dir is EXCLUDED from the materialized tree and must never cause a
        false block.
        """
        mod = _load_hook_module()
        repo = _build_codex_repo(tmp_path / "repo")

        # Working tree in sync: regenerate + commit the digest for tracked entries.
        _regenerate_digest(repo)
        _git(["add", "skills/second-opinion/codex-learnings-digest.md"], cwd=repo)
        _git(["commit", "-m", "chore: add digest"], cwd=repo)

        # Edit a TRACKED entry and regenerate so the tracked set stays in sync.
        entry = repo / "skills" / "second-opinion" / "codex-learnings.d" / "p01-phantom-symbol.md"
        entry.write_text(_ENTRY_P1.replace(
            "before writing the plan.",
            "before writing the plan, reliably.",
        ), encoding="utf-8")
        _regenerate_digest(repo)

        # Drop an UNTRACKED draft entry whose Design default is NOT in the digest.
        draft = repo / "skills" / "second-opinion" / "codex-learnings.d" / "20260620-120000-ab12-draft.md"
        draft.write_text(
            "# C2\n\n"
            "| ID | Pattern | Check |\n"
            "|----|---------|------|\n"
            "| C2 | Draft | Draft check |\n\n"
            "**Design default:** An UNTRACKED draft default not yet in the digest.\n",
            encoding="utf-8",
        )
        status = _git(["status", "--porcelain", "--", str(draft)], cwd=repo).stdout
        assert status.startswith("??"), status

        command = f'cd {repo} && git commit -am "fix: tweak p01"'
        # The untracked draft is excluded (ls-files) → no false block.
        assert mod.check_codex_digest_sync(command, str(repo)) is None

    def test_conservative_false_block_on_partial_staging(self, tmp_path):
        """DOCUMENTED CONSERVATIVE CASE: stage an in-sync snapshot, then modify a
        tracked entry unstaged → FIRES.

        This is the intentional conservative FALSE-BLOCK described in
        check_codex_digest_sync's docstring. The STAGED index holds an in-sync
        entry+digest pair (a plain `git commit` would commit only that, cleanly),
        but a further tracked-unstaged edit dirties the working tree. Because the
        grammar-free gate checks the TRACKED WORKING TREE (not the index), it
        conservatively BLOCKS. This is the correct failure direction for a safety
        gate (false-block is recoverable; false-allow ships a stale digest) and
        must NOT be "fixed" by re-introducing command-grammar parsing.
        """
        mod = _load_hook_module()
        repo = _build_codex_repo(tmp_path / "repo")

        # Stage an in-sync entry+digest snapshot.
        entry = repo / "skills" / "second-opinion" / "codex-learnings.d" / "p01-phantom-symbol.md"
        entry.write_text(_ENTRY_P1.replace(
            "before writing the plan.",
            "before writing the plan, staged version.",
        ), encoding="utf-8")
        _regenerate_digest(repo)
        _git(["add", "skills/second-opinion/codex-learnings.d/p01-phantom-symbol.md"], cwd=repo)
        _git(["add", "skills/second-opinion/codex-learnings-digest.md"], cwd=repo)

        # Now make a FURTHER unstaged edit to the entry that the staged digest
        # does NOT reflect → working tree is dirty + stale.
        entry.write_text(_ENTRY_P1.replace(
            "before writing the plan.",
            "before writing the plan, UNSTAGED edit the staged digest does not reflect.",
        ), encoding="utf-8")

        command = f'cd {repo} && git commit -m "fix: tweak p01"'
        block = mod.check_codex_digest_sync(command, str(repo))

        # Intentional conservative false-block: the tracked working tree is stale.
        assert block is not None, (
            "documented conservative case: a tracked-unstaged edit that stales the "
            "digest must FIRE the grammar-free working-tree gate"
        )
        assert "CODEX DIGEST STALE" in block

    def test_main_gate_beats_docs_only_exemption(self, run_hook, make_event, tmp_state_dir, tmp_path):
        """FIX 4: main() end-to-end — an entries-only commit with a stale digest is BLOCKED.

        Proves section-2.5 (the codex digest gate) preempts the section-3
        docs-only ``.md`` early-return: an edited entry is a ``.md`` file, so the
        docs-only exemption would otherwise skip all checks. Drives the hook's
        main() via the same run_hook/make_event harness the other main()-level
        tests use.
        """
        repo = _build_codex_repo(tmp_path / "repo")

        # In-sync digest committed, then an entry edited WITHOUT regenerating →
        # the committed digest is stale.
        _regenerate_digest(repo)
        _git(["add", "skills/second-opinion/codex-learnings-digest.md"], cwd=repo)
        _git(["commit", "-m", "chore: add digest"], cwd=repo)

        entry = repo / "skills" / "second-opinion" / "codex-learnings.d" / "p01-phantom-symbol.md"
        entry.write_text(_ENTRY_P1.replace(
            "**Design default:** Verify every symbol the plan names exists before writing the plan.\n",
            "**Design default:** A DIFFERENT default the stale digest does not reflect.\n",
        ), encoding="utf-8")
        _git(["add", "skills/second-opinion/codex-learnings.d/p01-phantom-symbol.md"], cwd=repo)

        # Sanity: ONLY the entry .md is staged (so docs-only would otherwise exempt).
        staged = _git(["diff", "--cached", "--name-only"], cwd=repo).stdout.split()
        assert staged == ["skills/second-opinion/codex-learnings.d/p01-phantom-symbol.md"], staged

        old = os.getcwd()
        os.chdir(str(repo))
        try:
            result = run_hook(
                "git-safety-guard.py",
                make_event("Bash", command=f'cd {repo} && git commit -m "docs: tweak p01"'),
            )
        finally:
            os.chdir(old)

        # main() must BLOCK with the stale-digest reason, NOT fall through the
        # docs-only exemption.
        assert "CODEX DIGEST STALE" in result.stdout, (
            f"main() did not block on stale digest (docs-only exemption leaked?): {result.stdout!r}"
        )

    def test_commit_gate_sees_test_and_lint_tokens_past_char_100(self, run_hook, make_event, tmp_state_dir, tmp_path):
        outer = tmp_path / "outer"
        outer.mkdir()
        _git(["init", "-b", "feat/x", str(outer)], cwd=outer.parent)
        (outer / "Makefile").touch()
        _git(["add", "Makefile"], cwd=outer)
        _git(["commit", "-m", "chore: init"], cwd=outer)
        (outer / "mod.py").write_text("x = 1\n")
        _git(["add", "mod.py"], cwd=outer)
        long_cmd = ("cd " + str(outer) + " && echo " + ("y" * 110)
                    + " && cargo test --workspace && cargo clippy --workspace")
        assert "cargo test" not in long_cmd[:100] and "clippy" not in long_cmd[:100]
        old = os.getcwd()
        os.chdir(str(outer))
        try:
            run_hook("git-safety-guard.py",
                     make_event("Bash", command=long_cmd, tool_result={"exit_code": 0}))
            result = run_hook("git-safety-guard.py",
                              make_event("Bash", command=f'cd {outer} && git commit -m "feat: add mod"'))
            assert result.stdout.strip() == "", f"gate false-failed: {result.stdout!r}"
        finally:
            os.chdir(old)


# ---------------------------------------------------------------------------
# Helpers for C5 test-hermeticity block adapter tests
# ---------------------------------------------------------------------------

_HOOK_PATH = Path(__file__).parent.parent / "git-safety-guard.py"


def _run_hook_with_env(event: dict, env: dict | None = None) -> dict | None:
    """Run git-safety-guard.py with optional extra env vars; return parsed JSON or None."""
    run_env = {**os.environ, **(env or {})}
    result = subprocess.run(
        ["python3", str(_HOOK_PATH)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        timeout=10,
        env=run_env,
    )
    try:
        return json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        return None


def _make_c5_git_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo on a non-protected branch, ready for staged content."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-b", "feat/c5-test", str(repo)], cwd=tmp_path)
    (repo / "README.md").write_text("# test repo\n")
    _git(["add", "README.md"], cwd=repo)
    _git(["commit", "-m", "chore: initial"], cwd=repo)
    return repo


def _stage_rust_file(repo: Path, name: str, content: str) -> None:
    """Write a Rust file to the repo and stage it."""
    (repo / name).write_text(content)
    _git(["add", name], cwd=repo)


# ---------------------------------------------------------------------------
# C5 test hermeticity block adapter — TestC5BlockHermeticity
# ---------------------------------------------------------------------------


class TestC5BlockHermeticity:
    """Integration tests for check_c5_test_hermeticity in git-safety-guard.py.

    All tests use real git tmp repos (no mocks for git). The sole exception is
    the detector-crash fail-open test which uses a pytest fixture to force a
    ValueError that real input cannot deterministically produce.
    """

    # ------------------------------------------------------------------
    # Must-not-fire negatives (staged .rs file → None, no block)
    # ------------------------------------------------------------------

    def test_no_block_ignored_axonservice_open(self, tmp_path):
        """#[ignore]-gated AxonService::open must NOT block (gold positive gated)."""
        repo = _make_c5_git_repo(tmp_path)
        content = (
            "#[cfg(test)]\nmod tests {\n"
            "    #[ignore = \"requires a real index\"]\n"
            "    #[tokio::test]\n"
            "    async fn test_open_real() {\n"
            "        let svc = AxonService::open(&repo_path);\n"
            "    }\n"
            "}\n"
        )
        _stage_rust_file(repo, "svc.rs", content)
        mod = _load_hook_module()
        result = mod.check_c5_test_hermeticity(
            f"cd {repo} && git commit -m \"feat: add test\"", str(repo)
        )
        assert result is None, f"Expected None for #[ignore]-gated open, got: {result!r}"

    def test_no_block_tempdir_database_open(self, tmp_path):
        """tempfile::tempdir() + Database::open is ephemeral — must NOT block."""
        repo = _make_c5_git_repo(tmp_path)
        content = (
            "#[cfg(test)]\nmod tests {\n"
            "    #[tokio::test]\n"
            "    async fn test_with_tempdir() {\n"
            "        let dir = tempfile::tempdir().unwrap();\n"
            "        let db = Database::open(dir.path());\n"
            "    }\n"
            "}\n"
        )
        _stage_rust_file(repo, "db.rs", content)
        mod = _load_hook_module()
        result = mod.check_c5_test_hermeticity(
            f"cd {repo} && git commit -m \"feat: add test\"", str(repo)
        )
        assert result is None, f"Expected None for tempdir-ephemeral open, got: {result!r}"

    def test_no_block_open_memory(self, tmp_path):
        """open_memory() is ephemeral — must NOT block."""
        repo = _make_c5_git_repo(tmp_path)
        content = (
            "#[cfg(test)]\nmod tests {\n"
            "    #[test]\n"
            "    fn test_in_memory() {\n"
            "        let db = Database::open_memory();\n"
            "    }\n"
            "}\n"
        )
        _stage_rust_file(repo, "mem.rs", content)
        mod = _load_hook_module()
        result = mod.check_c5_test_hermeticity(
            f"cd {repo} && git commit -m \"feat: add test\"", str(repo)
        )
        assert result is None, f"Expected None for open_memory, got: {result!r}"

    def test_no_block_cfg_attr_not_feature_ignore(self, tmp_path):
        """#[cfg_attr(not(feature=\"model-tests\"), ignore)] is a recognized gate — no block."""
        repo = _make_c5_git_repo(tmp_path)
        content = (
            "#[cfg(test)]\nmod tests {\n"
            "    #[cfg_attr(not(feature = \"model-tests\"), ignore)]\n"
            "    #[tokio::test]\n"
            "    async fn test_with_model() {\n"
            "        let emb = CandleEmbedder::new(model_path);\n"
            "    }\n"
            "}\n"
        )
        _stage_rust_file(repo, "embedder.rs", content)
        mod = _load_hook_module()
        result = mod.check_c5_test_hermeticity(
            f"cd {repo} && git commit -m \"feat: add test\"", str(repo)
        )
        assert result is None, f"Expected None for cfg_attr-ignore gate, got: {result!r}"

    # ------------------------------------------------------------------
    # Ungated synthesized violation → block message
    # ------------------------------------------------------------------

    def test_blocks_ungated_axonservice_open(self, tmp_path):
        """Bare #[tokio::test] + AxonService::open on a real path → block naming path + signature."""
        repo = _make_c5_git_repo(tmp_path)
        content = (
            "#[cfg(test)]\nmod tests {\n"
            "    #[tokio::test]\n"
            "    async fn test_open_real_index() {\n"
            "        let svc = AxonService::open(&real_index_path);\n"
            "    }\n"
            "}\n"
        )
        _stage_rust_file(repo, "svc_test.rs", content)
        mod = _load_hook_module()
        result = mod.check_c5_test_hermeticity(
            f"cd {repo} && git commit -m \"feat: add test\"", str(repo)
        )
        assert result is not None, "Expected block for ungated AxonService::open"
        assert "C5 TEST HERMETICITY" in result
        assert "svc_test.rs" in result
        assert "AxonService::open(" in result
        assert "#[ignore" in result  # fix hint present

    # ------------------------------------------------------------------
    # Per-function-scope regression
    # ------------------------------------------------------------------

    def test_derive_does_not_suppress_violation(self, tmp_path):
        """#[derive(Debug)] struct does NOT suppress an ungated test violation."""
        repo = _make_c5_git_repo(tmp_path)
        content = (
            "#[derive(Debug)]\n"
            "struct MyIndex { path: String }\n\n"
            "#[cfg(test)]\nmod tests {\n"
            "    #[tokio::test]\n"
            "    async fn test_open_real() {\n"
            "        let db = Database::open(&real_path);\n"
            "    }\n"
            "}\n"
        )
        _stage_rust_file(repo, "index.rs", content)
        mod = _load_hook_module()
        result = mod.check_c5_test_hermeticity(
            f"cd {repo} && git commit -m \"feat: add test\"", str(repo)
        )
        assert result is not None, "#[derive(Debug)] must NOT suppress a violation"
        assert "C5 TEST HERMETICITY" in result

    def test_mixed_file_gated_and_ungated(self, tmp_path):
        """File with one #[ignore]-gated test AND one ungated violation → blocks on the ungated."""
        repo = _make_c5_git_repo(tmp_path)
        content = (
            "#[cfg(test)]\nmod tests {\n"
            "    #[ignore = \"requires real index\"]\n"
            "    #[tokio::test]\n"
            "    async fn test_gated() {\n"
            "        let svc = AxonService::open(&real_path);\n"
            "    }\n\n"
            "    #[tokio::test]\n"
            "    async fn test_ungated() {\n"
            "        let svc = AxonService::open(&another_real_path);\n"
            "    }\n"
            "}\n"
        )
        _stage_rust_file(repo, "mixed.rs", content)
        mod = _load_hook_module()
        result = mod.check_c5_test_hermeticity(
            f"cd {repo} && git commit -m \"feat: add tests\"", str(repo)
        )
        assert result is not None, "Ungated violation must block even when a gated sibling exists"
        assert "C5 TEST HERMETICITY" in result

    # ------------------------------------------------------------------
    # Off-idiom traps → None (fail-open-safe FN)
    # ------------------------------------------------------------------

    def test_no_block_helper_wrapped_open(self, tmp_path):
        """Helper-wrapped open (no ::open( in test body) → None (off-idiom FN)."""
        repo = _make_c5_git_repo(tmp_path)
        content = (
            "fn open_real_service(path: &str) -> AxonService {\n"
            "    AxonService::open(path)\n"
            "}\n\n"
            "#[cfg(test)]\nmod tests {\n"
            "    #[tokio::test]\n"
            "    async fn test_via_helper() {\n"
            "        let svc = open_real_service(\"/real/path\");\n"
            "    }\n"
            "}\n"
        )
        _stage_rust_file(repo, "helper.rs", content)
        mod = _load_hook_module()
        result = mod.check_c5_test_hermeticity(
            f"cd {repo} && git commit -m \"feat: add test\"", str(repo)
        )
        assert result is None, f"Expected None for helper-wrapped open (off-idiom FN), got: {result!r}"

    def test_no_block_unrecognized_attribute_conservative_gate(self, tmp_path):
        """Unrecognized attribute on a test with an open → CONSERVATIVE-GATE → None."""
        repo = _make_c5_git_repo(tmp_path)
        content = (
            "#[cfg(test)]\nmod tests {\n"
            "    #[my_custom_skip_macro]\n"
            "    #[tokio::test]\n"
            "    async fn test_with_unknown_gate() {\n"
            "        let db = Database::open(&real_path);\n"
            "    }\n"
            "}\n"
        )
        _stage_rust_file(repo, "custom.rs", content)
        mod = _load_hook_module()
        result = mod.check_c5_test_hermeticity(
            f"cd {repo} && git commit -m \"feat: add test\"", str(repo)
        )
        assert result is None, f"Expected None for unrecognized attribute (conservative gate), got: {result!r}"

    # ------------------------------------------------------------------
    # (F2) Staged-only: unstaged violation must NOT block
    # ------------------------------------------------------------------

    def test_no_block_unstaged_violation(self, tmp_path):
        """Working-tree-only violation (unstaged) → commit must NOT block (staged index only)."""
        repo = _make_c5_git_repo(tmp_path)
        # Write violation but do NOT stage it
        content = (
            "#[cfg(test)]\nmod tests {\n"
            "    #[tokio::test]\n"
            "    async fn test_ungated() {\n"
            "        let db = Database::open(&real_path);\n"
            "    }\n"
            "}\n"
        )
        (repo / "unstaged.rs").write_text(content)
        # Stage a different (clean) file so the commit is non-empty
        (repo / "clean.rs").write_text("fn main() {}\n")
        _git(["add", "clean.rs"], cwd=repo)

        mod = _load_hook_module()
        result = mod.check_c5_test_hermeticity(
            f"cd {repo} && git commit -m \"feat: add clean\"", str(repo)
        )
        assert result is None, f"Unstaged violation must not block, got: {result!r}"

    # ------------------------------------------------------------------
    # (F1) Commit-only: git push must NOT trigger C5
    # ------------------------------------------------------------------

    def test_no_block_on_git_push(self, tmp_path):
        """git push with staged Rust violation → NO block (C5 gates on is_commit, not push).

        Tests the full hook subprocess to exercise the is_commit wiring gate in main()
        — calling the adapter directly bypasses the gate, so we must go via the hook.
        """
        repo = _make_c5_git_repo(tmp_path)
        content = (
            "#[cfg(test)]\nmod tests {\n"
            "    #[tokio::test]\n"
            "    async fn test_ungated() {\n"
            "        let svc = AxonService::open(&real_path);\n"
            "    }\n"
            "}\n"
        )
        _stage_rust_file(repo, "push_test.rs", content)
        event = {
            "tool_name": "Bash",
            "tool_input": {"command": f"cd {repo} && git push origin feat/c5-test"},
        }
        parsed = _run_hook_with_env(event)
        # Must NOT produce a C5 block (push bypasses is_commit gate in main()).
        if parsed is not None:
            assert parsed.get("decision") != "block" or "C5" not in parsed.get("reason", ""), (
                f"git push must not trigger C5 block, got: {parsed!r}"
            )

    def test_blocks_on_git_commit_with_same_violation(self, tmp_path):
        """Same staged violation → git commit DOES block via the full hook."""
        repo = _make_c5_git_repo(tmp_path)
        content = (
            "#[cfg(test)]\nmod tests {\n"
            "    #[tokio::test]\n"
            "    async fn test_ungated() {\n"
            "        let svc = AxonService::open(&real_path);\n"
            "    }\n"
            "}\n"
        )
        _stage_rust_file(repo, "commit_test.rs", content)
        event = {
            "tool_name": "Bash",
            "tool_input": {"command": f"cd {repo} && git commit -m \"feat: add test\""},
        }
        parsed = _run_hook_with_env(event)
        assert parsed is not None, "git commit with staged violation must block"
        assert parsed.get("decision") == "block", f"Expected block, got: {parsed!r}"
        assert "C5 TEST HERMETICITY" in parsed.get("reason", ""), (
            f"Expected C5 block reason, got: {parsed!r}"
        )

    # ------------------------------------------------------------------
    # (F2) Fail-open on detector crash
    # ------------------------------------------------------------------

    # mock-ok: forces ValueError from a simulated detector bug — real staged input cannot produce this
    def test_fail_open_on_detector_crash(self, tmp_path, monkeypatch):  # mock-ok: forces ValueError from simulated detector bug unreproducible with real input
        """Adapter returns None (not crash/block) when the detector raises an unexpected error."""
        repo = _make_c5_git_repo(tmp_path)
        content = (
            "#[cfg(test)]\nmod tests {\n"
            "    #[tokio::test]\n"
            "    async fn test_ungated() {\n"
            "        let svc = AxonService::open(&real_path);\n"
            "    }\n"
            "}\n"
        )
        _stage_rust_file(repo, "crash_test.rs", content)

        mod = _load_hook_module()

        # mock-ok: forces ValueError from simulated detector bug unreproducible with real input
        def _raise_value_error(text: str, lang: str):
            raise ValueError("simulated detector crash")

        monkeypatch.setattr(mod, "_c5_detect", _raise_value_error)  # mock-ok: forces ValueError from simulated detector bug unreproducible with real input
        result = mod.check_c5_test_hermeticity(
            f"cd {repo} && git commit -m \"feat: add test\"", str(repo)
        )
        assert result is None, f"Detector crash must fail open (return None), got: {result!r}"

    # ------------------------------------------------------------------
    # Infra fail-open: non-repo target → None
    # ------------------------------------------------------------------

    def test_fail_open_non_repo_target(self, tmp_path):
        """target_root not a git repo → None (infra fail-open)."""
        non_repo = tmp_path / "not_a_repo"
        non_repo.mkdir()
        mod = _load_hook_module()
        result = mod.check_c5_test_hermeticity(
            f"cd {non_repo} && git commit -m \"feat: add test\"", str(non_repo)
        )
        assert result is None, f"Non-repo target must fail open, got: {result!r}"

    # ------------------------------------------------------------------
    # Override: C5_ALLOW_UNGATED_TEST=1 → no block
    # ------------------------------------------------------------------

    def test_override_disables_block(self, tmp_path):
        """C5_ALLOW_UNGATED_TEST=1 with a real staged violation → no block."""
        repo = _make_c5_git_repo(tmp_path)
        content = (
            "#[cfg(test)]\nmod tests {\n"
            "    #[tokio::test]\n"
            "    async fn test_ungated() {\n"
            "        let svc = AxonService::open(&real_path);\n"
            "    }\n"
            "}\n"
        )
        _stage_rust_file(repo, "override_test.rs", content)
        event = {
            "tool_name": "Bash",
            "tool_input": {"command": f"cd {repo} && git commit -m \"feat: add test\""},
        }
        parsed = _run_hook_with_env(event, env={"C5_ALLOW_UNGATED_TEST": "1"})
        # Must NOT be a block decision (either None/empty stdout or non-block decision)
        if parsed is not None:
            assert parsed.get("decision") != "block", (
                f"Override must suppress C5 block, got: {parsed!r}"
            )

    # ------------------------------------------------------------------
    # Truncation: many violations → message bounded (~2000 + suffix)
    # ------------------------------------------------------------------

    def test_block_message_truncated_at_2000(self, tmp_path):
        """Many staged violations → block message length bounded (~2000 + suffix)."""
        repo = _make_c5_git_repo(tmp_path)
        # Stage many files with violations to produce a long findings list
        for i in range(30):
            name = f"test_{i:03d}_very_long_module_name_to_push_message_size.rs"
            content = (
                "#[cfg(test)]\nmod tests {\n"
                f"    #[tokio::test]\n"
                f"    async fn test_violation_{i}() {{\n"
                f"        let svc = AxonService::open(&real_path_{i});\n"
                "    }\n"
                "}\n"
            )
            _stage_rust_file(repo, name, content)

        mod = _load_hook_module()
        result = mod.check_c5_test_hermeticity(
            f"cd {repo} && git commit -m \"feat: add many tests\"", str(repo)
        )
        assert result is not None, "Expected block for many violations"
        assert len(result) <= 2000 + len("\n... (truncated)") + 10, (
            f"Message not bounded: len={len(result)}"
        )
