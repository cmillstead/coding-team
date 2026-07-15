"""Tests for git-safety-guard.py hook."""

import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

_HOOKS_DIR = Path(__file__).resolve().parent.parent  # tests/ -> hooks/
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))


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


def _init_feature_repo(path: Path) -> None:
    """Init a git repo at *path* on a non-protected branch, then touch a Makefile.

    hooks/tests/conftest.py roots tmp_path INSIDE the checkout (task #12), so a
    bare, git-less tmp_path is no longer guaranteed to resolve outside any repo:
    `git -C tmp_path rev-parse --show-toplevel` now walks up and finds the
    CHECKOUT's own .git, and is_protected_branch() then reports whatever branch
    the checkout happens to be on (main on a push-to-main CI run) instead of
    "not a repo". Giving each test its own git repo on a non-protected branch
    makes the branch check resolve deterministically regardless of the ambient
    checkout branch, mirroring _make_repo_on_branch used elsewhere in this file.
    No commit is needed — `git branch --show-current` and `rev-parse
    --show-toplevel` both resolve correctly on a freshly-initialized repo.
    """
    _git(["init", "-b", "feat/test", str(path)], cwd=path.parent)
    (path / "Makefile").touch()


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
        _init_feature_repo(tmp_path)
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
        _init_feature_repo(tmp_path)
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
        _init_feature_repo(tmp_path)
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
        _init_feature_repo(tmp_path)
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
        _init_feature_repo(tmp_path)
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
        _init_feature_repo(tmp_path)
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
        _init_feature_repo(tmp_path)
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
        _init_feature_repo(tmp_path)
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
        _init_feature_repo(tmp_path)
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
        _init_feature_repo(tmp_path)
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

    def test_advises_commit_when_tests_failed(self, run_hook, make_event, tmp_state_dir, tmp_path):
        """Commit is advisory (not blocked) when most recent test run had non-zero exit code."""
        _init_feature_repo(tmp_path)
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        _seed_verification_state(tmp_state_dir, test_exit_code=1, lint_exit_code=0)
        try:
            event = make_event("Bash", command='git commit -m "feat: add feature"')
            result = run_hook("git-safety-guard.py", event)
            assert result.parsed is not None
            assert result.parsed["decision"] == "allow"
            assert "FAILED" in result.parsed["reason"]
            assert "Tests failed" in result.parsed["reason"]
        finally:
            os.chdir(old_cwd)

    def test_advises_commit_when_lint_failed(self, run_hook, make_event, tmp_state_dir, tmp_path):
        """Commit is advisory (not blocked) when most recent lint run had non-zero exit code."""
        _init_feature_repo(tmp_path)
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        _seed_verification_state(tmp_state_dir, test_exit_code=0, lint_exit_code=1)
        try:
            event = make_event("Bash", command='git commit -m "feat: add feature"')
            result = run_hook("git-safety-guard.py", event)
            assert result.parsed is not None
            assert result.parsed["decision"] == "allow"
            assert "FAILED" in result.parsed["reason"]
            assert "Lint failed" in result.parsed["reason"]
        finally:
            os.chdir(old_cwd)

    def test_advises_commit_when_both_failed(self, run_hook, make_event, tmp_state_dir, tmp_path):
        """Commit is advisory (not blocked) when both test and lint runs failed."""
        _init_feature_repo(tmp_path)
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        _seed_verification_state(tmp_state_dir, test_exit_code=2, lint_exit_code=1)
        try:
            event = make_event("Bash", command='git commit -m "feat: add feature"')
            result = run_hook("git-safety-guard.py", event)
            assert result.parsed is not None
            assert result.parsed["decision"] == "allow"
            assert "Tests failed" in result.parsed["reason"]
            assert "Lint failed" in result.parsed["reason"]
        finally:
            os.chdir(old_cwd)

    def test_allows_commit_when_both_passed(self, run_hook, make_event, tmp_state_dir, tmp_path):
        """Commit allowed when both test and lint exit codes are 0."""
        _init_feature_repo(tmp_path)
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
        _init_feature_repo(tmp_path)
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
        _init_feature_repo(tmp_path)
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
        """Advisory message includes named rationalization about pre-existing failures."""
        _init_feature_repo(tmp_path)
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        _seed_verification_state(tmp_state_dir, test_exit_code=1, lint_exit_code=0)
        try:
            event = make_event("Bash", command='git commit -m "feat: add feature"')
            result = run_hook("git-safety-guard.py", event)
            assert result.parsed is not None
            assert result.parsed["decision"] == "allow"
            assert "pre-existing failure" in result.parsed["reason"].lower()
        finally:
            os.chdir(old_cwd)


class TestPostToolUseCapture:
    """Tests for PostToolUse behavior with the real tool_response schema."""

    def test_posttooluse_tool_response_event_no_exit_code_captured(
        self, run_hook, make_event, tmp_state_dir
    ):
        """Reality test: a real PostToolUse `tool_response`-keyed event does NOT produce
        a captured non-None exit code in state.

        Documents the REAL wire schema (01-02-PROBE-FINDING.md): CC delivers PostToolUse
        Bash results under `tool_response` (keys: stdout/stderr/interrupted/isImage/
        noOutputExpected — NO exit_code). Because git-safety-guard.py :752 discriminates
        Pre vs Post on `"tool_result" in ev`, a real `tool_response`-only event has NO
        `tool_result` key and is therefore routed to the PreToolUse branch, which records
        exit_code=None. This is WHY de-registering git-safety-guard from PostToolUse is
        safe: even if it received real PostToolUse events it could never capture exit codes
        from them. The hook cannot capture failures from real PostToolUse events.
        """
        import hashlib
        import json
        from pathlib import Path

        # Arrange: REAL PostToolUse wire shape — `tool_response` key, NO `tool_result`,
        # NO exit_code field. Build the dict literally (not via make_event, which only
        # adds `tool_result`).
        real_post_tool_use_event = {
            "tool_name": "Bash",
            "tool_input": {"command": "pytest tests/"},
            "tool_response": {
                "stdout": "FAILED test_foo.py::test_bar - AssertionError",
                "stderr": "",
                "interrupted": False,
                "isImage": False,
                "noOutputExpected": False,
                # NO exit_code — matches 01-02-PROBE-FINDING.md ground truth
            },
        }

        # Seed a prior state entry so the hook has a state file to append to
        _seed_verification_state(tmp_state_dir, test_exit_code=None, lint_exit_code=None)

        # Act: run the hook — no `tool_result` key → routes to PreToolUse branch,
        # tracks command with exit_code=None (the PreToolUse fallback behaviour)
        result = run_hook("git-safety-guard.py", real_post_tool_use_event)

        # The hook is silent (no JSON output) for a non-git command
        assert result.returncode == 0, f"Hook crashed: stderr={result.stderr!r}"
        assert result.stdout.strip() == "", (
            f"Hook should emit no output for this event; got: {result.stdout!r}"
        )

        # Assert: the captured exit code is None — the PreToolUse fallback records None
        # because no exit_code field existed on the real `tool_response` payload
        session_hash = hashlib.sha256(tmp_state_dir.encode()).hexdigest()[:12]
        state_file = Path(f"/tmp/claude-verification-{session_hash}.json")
        if state_file.exists():
            st = json.loads(state_file.read_text())
            verifications = st.get("verifications", [])
            pytest_entries = [v for v in verifications if "pytest" in v["command"]]
            if pytest_entries:
                last_pytest = pytest_entries[-1]
                assert last_pytest["exit_code"] is None, (
                    f"Expected exit_code=None (PreToolUse fallback, no exit_code on wire), "
                    f"got {last_pytest['exit_code']!r}"
                )

    def test_failed_state_produces_advisory_not_block_on_commit(
        self, run_hook, make_event, tmp_state_dir, tmp_path
    ):
        """A state with exit_code=1 recorded produces advisory (not block) on commit."""
        # Arrange: state with a failed pytest run (exit_code=1)
        _seed_verification_state(tmp_state_dir, test_exit_code=1, lint_exit_code=0)

        _init_feature_repo(tmp_path)
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            # Act: PreToolUse commit attempt
            ev = make_event("Bash", command='git commit -m "feat: something"')
            result = run_hook("git-safety-guard.py", ev)

            # Assert: advisory (allow + reason), NOT block
            assert result.parsed is not None, (
                f"Expected advisory JSON, got: {result.stdout!r}"
            )
            assert result.parsed["decision"] == "allow", (
                f"Expected advisory (allow), got decision={result.parsed['decision']!r}"
            )
            assert "FAILED" in result.parsed["reason"], (
                "Advisory reason should mention FAILED"
            )
        finally:
            os.chdir(old_cwd)

    def test_posttooluse_none_tool_result_does_not_crash(
        self, run_hook, make_event, tmp_state_dir
    ):
        """PostToolUse with None/string tool_result does not crash and stays silent."""
        # tool_result=None: make_event omits tool_result entirely — use a string instead
        # to exercise the string-path in _extract_exit_code
        ev = make_event("Bash", command="pytest tests/", tool_result="some output text")
        result = run_hook("git-safety-guard.py", ev)
        # Should be silent (no block, no crash)
        assert result.returncode == 0, f"Hook crashed: stderr={result.stderr!r}"
        assert result.stdout.strip() == "", (
            f"Expected silent output for string tool_result, got: {result.stdout!r}"
        )

    def test_posttooluse_missing_tool_result_no_output(
        self, run_hook, make_event, tmp_state_dir
    ):
        """PostToolUse event with no tool_result field (omitted) is treated as PreToolUse.

        Codifies the dormant discriminator: git-safety-guard.py :752 gates on
        `"tool_result" in ev`; a real PostToolUse event (which carries `tool_response`,
        not `tool_result`) therefore falls through to the PreToolUse branch. This is
        consistent with git-safety-guard being de-registered from PostToolUse — it was
        never routing real PostToolUse events correctly anyway.
        """
        # When tool_result is not in the event, the hook treats it as PreToolUse.
        # A non-git command should produce no output (silent pass-through).
        ev = make_event("Bash", command="pytest tests/")
        # No tool_result key → PreToolUse path → tracks as verification, no output
        result = run_hook("git-safety-guard.py", ev)
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_missing_verification_still_blocks(
        self, run_hook, make_event, tmp_state_dir, tmp_path
    ):
        """Regression: no recent test/lint verification → missing path still BLOCKS."""
        import hashlib
        from pathlib import Path

        # Arrange: empty/no state file (no verification run at all)
        session_hash = hashlib.sha256(tmp_state_dir.encode()).hexdigest()[:12]
        state_file = Path(f"/tmp/claude-verification-{session_hash}.json")
        if state_file.exists():
            state_file.unlink()

        _init_feature_repo(tmp_path)
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            ev = make_event("Bash", command='git commit -m "feat: untested change"')
            result = run_hook("git-safety-guard.py", ev)

            # Assert: hard BLOCK (missing path, not advisory)
            assert result.parsed is not None, (
                f"Expected block JSON, got: {result.stdout!r}"
            )
            assert result.parsed["decision"] == "block", (
                f"Expected block for missing verification, got {result.parsed['decision']!r}"
            )
            assert "NOT run" in result.parsed["reason"] or "MUST run" in result.parsed["reason"], (
                f"Expected 'NOT run'/'MUST run' in block reason: {result.parsed['reason']!r}"
            )
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


# Real-shaped entry: a single '**Design default:**' line is required by
# build-digest.py's design face, and the 3rd table column is required by its
# review face — header text MUST be the real "Check before dispatch" (not the
# abbreviated "Check") so review-face extraction succeeds on these fixtures.
_ENTRY_P1 = (
    "# P1\n\n"
    "| ID | Pattern | Check before dispatch |\n"
    "|----|---------|----------------------|\n"
    "| P1 | Phantom symbol | Grep for every named symbol. |\n\n"
    "**Design default:** Verify every symbol the plan names exists before writing the plan.\n"
)

_ENTRY_C1 = (
    "# C1\n\n"
    "| ID | Pattern | Check before dispatch |\n"
    "|----|---------|----------------------|\n"
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
    """Run the real build-digest.py (no --check) to write an in-sync design digest."""
    script = root / "skills" / "second-opinion" / "scripts" / "build-digest.py"
    subprocess.run(["python3", str(script)], check=True, capture_output=True, text=True)


def _regenerate_review_digest(root: Path) -> None:
    """Run the real build-digest.py --face review (no --check) to write an in-sync review digest."""
    script = root / "skills" / "second-opinion" / "scripts" / "build-digest.py"
    subprocess.run(
        ["python3", str(script), "--face", "review"], check=True, capture_output=True, text=True
    )


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
        """(b) entry committed with BOTH digests correctly regenerated → None (allowed)."""
        mod = _load_hook_module()
        repo = _build_codex_repo(tmp_path / "repo")

        # Edit an entry AND regenerate BOTH digests so they are in sync, stage all.
        entry = repo / "skills" / "second-opinion" / "codex-learnings.d" / "p01-phantom-symbol.md"
        entry.write_text(_ENTRY_P1.replace(
            "before writing the plan.",
            "before writing the plan, every time.",
        ), encoding="utf-8")
        _regenerate_digest(repo)
        _regenerate_review_digest(repo)
        _git(["add", "skills/second-opinion/codex-learnings.d/p01-phantom-symbol.md"], cwd=repo)
        _git(["add", "skills/second-opinion/codex-learnings-digest.md"], cwd=repo)
        _git(["add", "skills/second-opinion/codex-learnings-review-digest.md"], cwd=repo)

        command = f'cd {repo} && git commit -m "fix: tweak p01 and regen"'
        assert mod.check_codex_digest_sync(command, str(repo)) is None

    def test_both_faces_clean_returns_none(self, tmp_path):
        """BOTH faces clean → allow. Named explicitly per the design/review two-face gate."""
        mod = _load_hook_module()
        repo = _build_codex_repo(tmp_path / "repo")

        entry = repo / "skills" / "second-opinion" / "codex-learnings.d" / "p01-phantom-symbol.md"
        entry.write_text(_ENTRY_P1.replace(
            "before writing the plan.",
            "before writing the plan, in both faces.",
        ), encoding="utf-8")
        _regenerate_digest(repo)
        _regenerate_review_digest(repo)
        _git(["add", "skills/second-opinion/codex-learnings.d/p01-phantom-symbol.md"], cwd=repo)
        _git(["add", "skills/second-opinion/codex-learnings-digest.md"], cwd=repo)
        _git(["add", "skills/second-opinion/codex-learnings-review-digest.md"], cwd=repo)

        command = f'cd {repo} && git commit -m "fix: tweak p01, both digests in sync"'
        assert mod.check_codex_digest_sync(command, str(repo)) is None

    def test_design_clean_review_stale_blocks(self, tmp_path):
        """design digest clean, review digest STALE → block (no early return after design passes).

        Editing ONLY the check-face table cell (leaving the Design default
        sentence untouched) leaves the design render byte-identical to the
        committed baseline (design stays clean) while the review render now
        diverges from the committed baseline (review goes stale). Proves
        19b2: the design face passing must NOT short-circuit the review check.
        """
        mod = _load_hook_module()
        repo = _build_codex_repo(tmp_path / "repo")

        # Establish an in-sync BASELINE for both faces and commit them.
        _regenerate_digest(repo)
        _regenerate_review_digest(repo)
        _git(["add", "skills/second-opinion/codex-learnings-digest.md"], cwd=repo)
        _git(["add", "skills/second-opinion/codex-learnings-review-digest.md"], cwd=repo)
        _git(["commit", "-m", "chore: add both digests"], cwd=repo)

        # Edit ONLY the check-face table cell; the Design default sentence is
        # untouched, so the design render still matches the committed baseline.
        # Deliberately do NOT regenerate either digest — the review digest now
        # diverges from this edit; the design digest still matches (nothing
        # about the Design default line changed).
        entry = repo / "skills" / "second-opinion" / "codex-learnings.d" / "p01-phantom-symbol.md"
        entry.write_text(_ENTRY_P1.replace(
            "| P1 | Phantom symbol | Grep for every named symbol. |",
            "| P1 | Phantom symbol | Grep for every named symbol, always. |",
        ), encoding="utf-8")
        _git(["add", "skills/second-opinion/codex-learnings.d/p01-phantom-symbol.md"], cwd=repo)

        command = f'cd {repo} && git commit -m "fix: tweak p01 check face only"'
        block = mod.check_codex_digest_sync(command, str(repo))

        assert block is not None, "review face must independently block even when design is clean"
        assert "CODEX DIGEST STALE" in block
        assert "[review face]" in block
        assert "codex-learnings-review-digest.md" in block
        assert "[design face]" not in block, "design face is clean and must not be listed as stale"

    def test_design_stale_review_clean_blocks(self, tmp_path):
        """design digest STALE, review digest clean → block (no early return after review passes).

        Editing ONLY the Design default sentence (leaving the check-face table
        cell untouched) leaves the review render byte-identical to the
        committed baseline (review stays clean) while the design render now
        diverges from the committed baseline (design goes stale). Proves
        19b2: the review face passing must NOT short-circuit the design check.
        """
        mod = _load_hook_module()
        repo = _build_codex_repo(tmp_path / "repo")

        # Establish an in-sync BASELINE for both faces and commit them.
        _regenerate_digest(repo)
        _regenerate_review_digest(repo)
        _git(["add", "skills/second-opinion/codex-learnings-digest.md"], cwd=repo)
        _git(["add", "skills/second-opinion/codex-learnings-review-digest.md"], cwd=repo)
        _git(["commit", "-m", "chore: add both digests"], cwd=repo)

        # Edit ONLY the Design default sentence; the check-face table cell is
        # untouched, so the review render still matches the committed baseline.
        # Deliberately do NOT regenerate either digest — the design digest now
        # diverges from this edit; the review digest still matches.
        entry = repo / "skills" / "second-opinion" / "codex-learnings.d" / "p01-phantom-symbol.md"
        entry.write_text(_ENTRY_P1.replace(
            "**Design default:** Verify every symbol the plan names exists before writing the plan.\n",
            "**Design default:** A DIFFERENT default; the check-face cell text is untouched.\n",
        ), encoding="utf-8")
        _git(["add", "skills/second-opinion/codex-learnings.d/p01-phantom-symbol.md"], cwd=repo)

        command = f'cd {repo} && git commit -m "fix: tweak p01 design default only"'
        block = mod.check_codex_digest_sync(command, str(repo))

        assert block is not None, "design face must independently block even when review is clean"
        assert "CODEX DIGEST STALE" in block
        assert "[design face]" in block
        assert "codex-learnings-digest.md" in block
        assert "[review face]" not in block, "review face is clean and must not be listed as stale"

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
        """FIX A: `git commit -am` with the working tree in sync (BOTH digests) → None (allowed)."""
        mod = _load_hook_module()
        repo = _build_codex_repo(tmp_path / "repo")

        # Commit in-sync digests so the entry AND both digests are TRACKED
        # (a -a commit only captures tracked modifications; the digests must
        # be tracked to be part of the to-be-committed tree).
        _regenerate_digest(repo)
        _regenerate_review_digest(repo)
        _git(["add", "skills/second-opinion/codex-learnings-digest.md"], cwd=repo)
        _git(["add", "skills/second-opinion/codex-learnings-review-digest.md"], cwd=repo)
        _git(["commit", "-m", "chore: add digests"], cwd=repo)

        # Edit the tracked entry, regenerate BOTH digests so the WORKING TREE is
        # in sync, stage NOTHING (a -a commit captures tracked modifications).
        entry = repo / "skills" / "second-opinion" / "codex-learnings.d" / "p01-phantom-symbol.md"
        entry.write_text(_ENTRY_P1.replace(
            "before writing the plan.",
            "before writing the plan, consistently.",
        ), encoding="utf-8")
        _regenerate_digest(repo)
        _regenerate_review_digest(repo)

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

        # Working tree is in sync: regenerate BOTH digests for the tracked entries.
        _regenerate_digest(repo)
        _regenerate_review_digest(repo)
        _git(["add", "skills/second-opinion/codex-learnings-digest.md"], cwd=repo)
        _git(["add", "skills/second-opinion/codex-learnings-review-digest.md"], cwd=repo)
        _git(["commit", "-m", "chore: add digests"], cwd=repo)

        # Edit a TRACKED entry and regenerate so the tracked set stays in sync;
        # stage nothing (a -a commit captures tracked modifications).
        entry = repo / "skills" / "second-opinion" / "codex-learnings.d" / "p01-phantom-symbol.md"
        entry.write_text(_ENTRY_P1.replace(
            "before writing the plan.",
            "before writing the plan, reliably.",
        ), encoding="utf-8")
        _regenerate_digest(repo)
        _regenerate_review_digest(repo)

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

        # Working tree in sync: regenerate + commit BOTH digests for tracked entries.
        _regenerate_digest(repo)
        _regenerate_review_digest(repo)
        _git(["add", "skills/second-opinion/codex-learnings-digest.md"], cwd=repo)
        _git(["add", "skills/second-opinion/codex-learnings-review-digest.md"], cwd=repo)
        _git(["commit", "-m", "chore: add digests"], cwd=repo)

        # Edit a TRACKED entry and regenerate so the tracked set stays in sync.
        entry = repo / "skills" / "second-opinion" / "codex-learnings.d" / "p01-phantom-symbol.md"
        entry.write_text(_ENTRY_P1.replace(
            "before writing the plan.",
            "before writing the plan, reliably.",
        ), encoding="utf-8")
        _regenerate_digest(repo)
        _regenerate_review_digest(repo)

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
# Tests for compound-hygiene warn-mode advisory (Increment 1)
# ---------------------------------------------------------------------------

class TestCompoundHygieneAdvisory:
    """Updated for A2 deny posture: multi-statement compounds are BLOCKED, not warned.

    This class previously tested the Increment 1 warn-only advisory
    (_emit_compound_hygiene_advisory_if_unknown). With the deny posture,
    all multi-statement compounds are BLOCKED unless they are a blessed
    VAR=$(allowlisted-single) value-capture. The advisory path is replaced by
    a hard block with an actionable message.
    """

    @staticmethod
    def _known_atom():
        """Return a simple single-statement atom for use in compound tests.

        These tests need a command that, when used in a compound (e.g. `cmd && other`),
        triggers the deny path. Any single atom works — the hook blocks ALL non-blessed
        multi-statement compounds regardless of allowlist membership.
        """
        return "echo checking"

    def test_unknown_atom_compound_now_blocks(self, run_hook, make_event):
        # A2 deny posture: a known atom chained with an unknown binary → BLOCK.
        # The old warn-only path emitted permissionDecision:"ask"; the new path
        # emits a hard block with an actionable message.
        known = self._known_atom()
        cmd = f"{known} && zzznotarealbinary --version"
        result = run_hook("git-safety-guard.py", make_event("Bash", command=cmd))
        assert result.returncode == 0, f"hook crashed: {result.stderr!r}"
        assert result.parsed is not None, (
            f"block did NOT fire (no JSON emitted). stdout={result.stdout!r}"
        )
        assert result.parsed.get("decision") == "block", (
            f"expected block for unknown-atom compound, got {result.parsed!r}"
        )
        assert "One command per Bash call" in result.parsed.get("reason", ""), (
            f"block reason must be actionable: {result.parsed!r}"
        )

    def test_non_gated_compound_always_blocks_regardless_of_allowlist(self, run_hook, make_event):
        # A2: even an all-allowlisted compound (not a blessed value-capture) is BLOCKED.
        # The old auto-allow fold (_emit_compound_allow_if_safe) is gone.
        known = self._known_atom()
        cmd = f"{known} && {known}"
        result = run_hook("git-safety-guard.py", make_event("Bash", command=cmd))
        assert result.returncode == 0, f"hook crashed: {result.stderr!r}"
        assert result.parsed is not None, (
            f"block did NOT fire for all-known compound. stdout={result.stdout!r}"
        )
        assert result.parsed.get("decision") == "block", (
            f"expected block for non-blessed compound, got {result.parsed!r}"
        )
        assert "One command per Bash call" in result.parsed.get("reason", "")

    def test_single_command_unaffected(self, run_hook, make_event):
        result = run_hook("git-safety-guard.py", make_event("Bash", command="git status"))
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_gated_git_compound_routed_to_branch_verify_not_deny_path(self, run_hook, make_event, tmp_path):
        # A compound containing a gated git op (commit) goes to the branch/verify path.
        # The deny path skips it (_has_gated_git_op → True). On a feature branch the
        # deny block "One command per Bash call" must NOT appear.
        repo = tmp_path / "repo"
        repo.mkdir()
        _make_repo_on_branch(repo, branch="feature/x")
        old_cwd = os.getcwd()
        os.chdir(str(repo))
        try:
            cmd = f"cd {repo} && git commit -m 'feat: x' && zzznotarealbinary run"
            result = run_hook("git-safety-guard.py", make_event("Bash", command=cmd))
            assert result.returncode == 0
            # Must NOT emit the deny-path "One command per Bash call" block.
            assert "One command per Bash call" not in result.stdout, (
                f"Deny path must not fire on gated-git compound: {result.stdout!r}"
            )
        finally:
            os.chdir(old_cwd)

    def test_redirect_is_not_multi_statement_fails_open(self, run_hook, make_event):
        # Redirects (> / <) are NOT in _MULTI_SIGNALS; is_multi_statement returns False.
        # The deny path falls through for redirects — fail-open behavior preserved.
        cmd = "echo hi > /tmp/zzz_test_out.txt"
        result = run_hook("git-safety-guard.py", make_event("Bash", command=cmd))
        assert result.returncode == 0
        # A redirect is NOT flagged as multi-statement; deny path falls through.
        if result.parsed is not None:
            assert "One command per Bash call" not in result.parsed.get("reason", ""), (
                f"Deny path must not fire on redirect: {result.parsed!r}"
            )

    def test_deny_path_never_crashes_on_garbage(self, run_hook, make_event):
        # Self-guard: _deny_compound_unless_blessed catches all exceptions → False.
        # Garbage that is multi-statement may block; garbage that triggers an exception
        # falls through. Either way the hook must not crash (returncode == 0).
        for cmd in ["$(", "`", ";;;", "&& ||", "echo a && ", "()", "><"]:
            result = run_hook("git-safety-guard.py", make_event("Bash", command=cmd))
            assert result.returncode == 0, f"crashed on {cmd!r}: {result.stderr!r}"


# ---------------------------------------------------------------------------
# Tests for _deny_compound_unless_blessed (A2: deny posture for compounds)
# ---------------------------------------------------------------------------

class TestDenyCompoundUnlessBlessed:
    """Tests for _deny_compound_unless_blessed — the new §4 deny path.

    Phase 1 (dormant): tests invoke the function directly via _load_hook_module()
    so they validate the function's logic before it is wired into main().
    Phase 2 integration tests (run_hook) become meaningful after the §4 wiring.
    """

    def _fn(self):
        """Return the _deny_compound_unless_blessed function."""
        return _load_hook_module()._deny_compound_unless_blessed

    # --- Non-git multi-statement → block emitted ---

    def test_pipe_is_blocked(self, run_hook, make_event):
        """ls | wc -l is multi-statement and non-git → block after wiring."""
        fn = self._fn()
        # Non-vacuous: assert the function returns True (decision emitted) for a pipe.
        # We capture stdout to check it emits a block.
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = fn("ls | wc -l")
        assert result is True
        output_text = buf.getvalue()
        parsed = json.loads(output_text)
        assert parsed["decision"] == "block"
        assert "One command per Bash call" in parsed["reason"]

    def test_and_and_is_blocked(self, run_hook, make_event):
        """a && b is multi-statement and non-git → block."""
        fn = self._fn()
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = fn("a && b")
        assert result is True
        parsed = json.loads(buf.getvalue())
        assert parsed["decision"] == "block"
        assert "One command per Bash call" in parsed["reason"]

    def test_for_loop_is_blocked(self, run_hook, make_event):
        """for f in *; do x; done is multi-statement and non-git → block."""
        fn = self._fn()
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = fn("for f in *; do x; done")
        assert result is True
        parsed = json.loads(buf.getvalue())
        assert parsed["decision"] == "block"
        assert "One command per Bash call" in parsed["reason"]

    # --- Blessed value-capture → falls through to prompt (no block, no auto-allow) ---

    def test_blessed_capture_falls_through(self, run_hook, make_event):
        """REPO=$(git rev-parse --show-toplevel) — blessed shape → no decision emitted (prompt)."""
        fn = self._fn()
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = fn("REPO=$(git rev-parse --show-toplevel)")
        # Returns False (no decision emitted) — falls through to CC prompt
        assert result is False, "Blessed value-capture must fall through (return False, no auto-allow)"
        output_text = buf.getvalue().strip()
        assert output_text == "", f"No output expected for blessed fall-through, got: {output_text!r}"

    # --- Blessed but inner NOT allowlisted → NEITHER block NOR allow ---

    def test_blessed_unlisted_inner_falls_through(self):
        """X=$(some-unlisted-tool) — blessed shape but inner not allowlisted → no decision."""
        fn = self._fn()
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = fn("X=$(zzznotarealtool123)")
        # Returns False (no decision emitted)
        assert result is False, "Blessed but unlisted inner must fall through (return False)"
        # Non-vacuous: assert BOTH no block AND no allow in output
        output_text = buf.getvalue().strip()
        assert output_text == "", f"No output expected for fall-through, got: {output_text!r}"

    # --- Blessed captures of any kind → fall through to prompt ---

    def test_bash_capture_falls_through(self):
        """X=$(bash --version) — blessed shape (no compound inner) → falls through to prompt."""
        fn = self._fn()
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = fn("X=$(bash --version)")
        # Returns False (no decision emitted) — falls through to CC prompt
        assert result is False, "Blessed value-capture must fall through (return False)"
        output_text = buf.getvalue().strip()
        assert output_text == "", f"No output expected for fall-through, got: {output_text!r}"

    # --- Single command → no output ---

    def test_single_git_status_falls_through(self):
        """git status is NOT multi-statement → function returns False immediately."""
        fn = self._fn()
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = fn("git status")
        assert result is False
        assert buf.getvalue().strip() == ""

    def test_single_wc_falls_through(self):
        """wc -l file is NOT multi-statement → function returns False immediately."""
        fn = self._fn()
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = fn("wc -l file")
        assert result is False
        assert buf.getvalue().strip() == ""

    # --- Gated-git compound → deny path does NOT fire ---

    def test_gated_git_compound_skipped(self):
        """cd /repo && git commit -m 'feat: x' → _has_gated_git_op True → returns False."""
        fn = self._fn()
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = fn("cd /repo && git commit -m 'feat: x'")
        assert result is False, "Gated-git compound must return False (deny path does not fire)"
        output_text = buf.getvalue().strip()
        # Non-vacuous: confirm NO "One command per Bash call" block from the deny path
        assert "One command per Bash call" not in output_text

    # --- Exception safety ---

    def test_never_raises_on_garbage(self):
        """Self-guard: any exception returns False (fall through, never block-closed)."""
        fn = self._fn()
        for cmd in ["", "$(", "`", ";;;", "&& ||"]:
            result = fn(cmd)
            assert isinstance(result, bool), f"Expected bool for {cmd!r}, got {type(result)}"

    # --- Integration tests via run_hook (pass after §4 wiring) ---

    def test_pipe_blocked_via_hook(self, run_hook, make_event):
        """Integration: ls | wc -l → hook emits block after §4 is wired."""
        result = run_hook("git-safety-guard.py", make_event("Bash", command="ls | wc -l"))
        assert result.returncode == 0
        assert result.parsed is not None, f"Expected block JSON, got: {result.stdout!r}"
        assert result.parsed.get("decision") == "block"
        assert "One command per Bash call" in result.parsed.get("reason", "")

    def test_and_and_blocked_via_hook(self, run_hook, make_event):
        """Integration: a && b → hook emits block after §4 is wired."""
        result = run_hook("git-safety-guard.py", make_event("Bash", command="a && b"))
        assert result.returncode == 0
        assert result.parsed is not None, f"Expected block JSON, got: {result.stdout!r}"
        assert result.parsed.get("decision") == "block"
        assert "One command per Bash call" in result.parsed.get("reason", "")

    def test_for_loop_blocked_via_hook(self, run_hook, make_event):
        """Integration: for f in *; do x; done → hook emits block after §4 is wired."""
        result = run_hook("git-safety-guard.py", make_event("Bash", command="for f in *; do x; done"))
        assert result.returncode == 0
        assert result.parsed is not None, f"Expected block JSON, got: {result.stdout!r}"
        assert result.parsed.get("decision") == "block"
        assert "One command per Bash call" in result.parsed.get("reason", "")

    def test_blessed_capture_falls_through_via_hook(self, run_hook, make_event):
        """Integration: REPO=$(git rev-parse --show-toplevel) → no decision (falls through to prompt)."""
        result = run_hook(
            "git-safety-guard.py",
            make_event("Bash", command="REPO=$(git rev-parse --show-toplevel)"),
        )
        assert result.returncode == 0
        # No block, no auto-allow — silent fall-through to CC permission prompt
        assert result.stdout.strip() == "", (
            f"Blessed value-capture must produce no output (prompt, not auto-allow), "
            f"got: {result.stdout!r}"
        )

    def test_unlisted_blessed_capture_no_block_no_allow_via_hook(self, run_hook, make_event):
        """Integration: X=$(zzznotarealtool) → neither block nor allow after §4 is wired."""
        result = run_hook(
            "git-safety-guard.py",
            make_event("Bash", command="X=$(zzznotarealtool123456)"),
        )
        assert result.returncode == 0
        # Non-vacuous: assert BOTH absent — no block and no allow decision
        if result.parsed is not None:
            assert result.parsed.get("decision") != "block", (
                f"Fall-through must not produce a block, got: {result.parsed!r}"
            )
            hso = result.parsed.get("hookSpecificOutput", {})
            assert hso.get("permissionDecision") != "allow", (
                f"Fall-through must not produce an allow, got: {result.parsed!r}"
            )

    def test_bash_capture_falls_through_via_hook(self, run_hook, make_event):
        """Integration: X=$(bash --version) → falls through (blessed shape, no compound inner).

        X=$(bash --version) is a blessed value-capture (single-statement inner).
        The hook produces no output — it falls through to the CC permission prompt.
        Neither a block nor an auto-allow is emitted.
        """
        result = run_hook(
            "git-safety-guard.py",
            make_event("Bash", command="X=$(bash --version)"),
        )
        assert result.returncode == 0
        # No block, no auto-allow — falls through to CC prompt
        assert result.stdout.strip() == "", (
            f"Blessed value-capture must produce no output (prompt), got: {result.stdout!r}"
        )

    def test_single_command_no_output_via_hook(self, run_hook, make_event):
        """Integration: git status → no output (single command, not multi-statement)."""
        result = run_hook("git-safety-guard.py", make_event("Bash", command="git status"))
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_gated_git_compound_no_deny_path_block_via_hook(self, run_hook, make_event, tmp_path):
        """Integration: cd /repo && git commit → deny path does NOT fire; no 'One command per Bash call'."""
        # Use a feature-branch repo so the branch guard does not block
        repo = tmp_path / "repo"
        repo.mkdir()
        _make_repo_on_branch(repo, branch="feature/test-deny-path")
        old_cwd = os.getcwd()
        os.chdir(str(repo))
        try:
            cmd = f"cd {repo} && git commit -m 'feat: x'"
            result = run_hook("git-safety-guard.py", make_event("Bash", command=cmd))
            assert result.returncode == 0
            # The deny path must NOT emit the "One command per Bash call" block
            assert "One command per Bash call" not in result.stdout, (
                f"Deny path fired on gated-git compound: {result.stdout!r}"
            )
        finally:
            os.chdir(old_cwd)


@contextlib.contextmanager
def _env_override(key: str, value: str | None):
    """Temporarily set (value given) or unset (value None) an env var; restore after.

    Direct os.environ save/restore — mirrors conftest.py's tmp_state_dir fixture
    idiom. subprocess.run inherits the current process env when no explicit
    `env=` kwarg is passed, so this also covers run_hook subprocess calls made
    inside the `with` block.
    """
    old = os.environ.get(key)
    if value is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = value
    try:
        yield
    finally:
        if old is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = old


class TestCompoundAllowOverride:
    """GIT_SAFETY_ALLOW_COMPOUND disables the compound block UNCONDITIONALLY.

    Every multi-statement compound falls through to CC's normal permission
    handling when the flag is set — including a command that references a literal
    "git" token anywhere (e.g. inside a quoted free-text argument, or a plain
    `git status ... | head`). The git-op guards (secret/branch/verify/format) that
    run earlier in main() are untouched and still gate add/commit/push/merge
    regardless of this flag.
    """

    def _fn(self):
        return _load_hook_module()._deny_compound_unless_blessed

    def test_flag_set_lets_nongit_compound_fall_through(self):
        buf = io.StringIO()
        with _env_override("GIT_SAFETY_ALLOW_COMPOUND", "1"):
            with contextlib.redirect_stdout(buf):
                result = self._fn()("ls | head")
        assert result is False, "non-git compound must fall through when flag set"
        assert buf.getvalue().strip() == "", (
            f"no output expected when override active, got: {buf.getvalue()!r}"
        )

    def test_flag_set_nongit_compound_falls_through_subprocess(self, run_hook, make_event):
        with _env_override("GIT_SAFETY_ALLOW_COMPOUND", "1"):
            result = run_hook("git-safety-guard.py", make_event("Bash", command="ls | head"))
        assert result.returncode == 0, f"hook must exit 0, got {result.returncode}; stderr={result.stderr!r}"
        assert result.stdout.strip() == "", f"fall-through must emit no output, got: {result.stdout!r}"
        assert result.parsed is None, (
            f"non-git compound must fall through in subprocess with flag set, "
            f"got block: {result.stdout!r}"
        )

    def test_flag_set_codex_exec_quoted_git_mention_falls_through(self):
        """REGRESSION: a `codex exec` prompt with a quoted 'git' mention must not
        re-block when the override is set. This is the exact shape that defeated
        the operator's opt-out: a git token inside a quoted free-text argument."""
        cmd = (
            'codex exec -C /some/path "Review the plan; check git history; '
            'Focus on: 1. correctness (handles X)"'
        )
        buf = io.StringIO()
        with _env_override("GIT_SAFETY_ALLOW_COMPOUND", "1"):
            with contextlib.redirect_stdout(buf):
                result = self._fn()(cmd)
        assert result is False, "quoted git mention must not re-trigger the deny path"
        assert buf.getvalue().strip() == "", (
            f"no block output expected when override active, got: {buf.getvalue()!r}"
        )

    def test_flag_set_git_status_pipe_falls_through(self):
        """REGRESSION: `git status --short --branch | head -5` with the override set
        must fall through — the exact command shape that failed for the operator
        (a real git token plus a non-gated pipe)."""
        cmd = "git status --short --branch | head -5"
        buf = io.StringIO()
        with _env_override("GIT_SAFETY_ALLOW_COMPOUND", "1"):
            with contextlib.redirect_stdout(buf):
                result = self._fn()(cmd)
        assert result is False, (
            "git-mentioning non-gated compound must fall through when override is set"
        )
        assert buf.getvalue().strip() == "", (
            f"no block output expected when override active, got: {buf.getvalue()!r}"
        )

    def test_flag_set_git_status_pipe_falls_through_subprocess(self, run_hook, make_event):
        """Integration: same as above, via the real subprocess hook invocation."""
        with _env_override("GIT_SAFETY_ALLOW_COMPOUND", "1"):
            result = run_hook(
                "git-safety-guard.py",
                make_event("Bash", command="git status --short --branch | head -5"),
            )
        assert result.returncode == 0, f"hook must exit 0, got {result.returncode}; stderr={result.stderr!r}"
        assert result.stdout.strip() == "", f"fall-through must emit no output, got: {result.stdout!r}"
        assert result.parsed is None, (
            f"git-mentioning compound must fall through in subprocess with flag set, "
            f"got block: {result.stdout!r}"
        )

    @pytest.mark.parametrize("cmd", [
        "git -C /repo add .env && echo done",
        "GIT -C /repo add .env && echo done",
    ])
    def test_parsermiss_git_compound_falls_through_when_flag_set(self, cmd):
        """FLIPPED: the override is now unconditional — a git token (even one the
        gated-op regex misses, e.g. `git -C /repo add`) no longer re-triggers the
        deny path. Real protection for this parser-miss shape is a documented,
        accepted gap (see COMPOUND_ALLOW_OVERRIDE_ENV docstring), not this hook."""
        buf = io.StringIO()
        with _env_override("GIT_SAFETY_ALLOW_COMPOUND", "1"):
            with contextlib.redirect_stdout(buf):
                result = self._fn()(cmd)
        assert result is False, f"override is unconditional; must fall through: {cmd!r}"
        assert buf.getvalue().strip() == "", (
            f"no block output expected when override active, got: {buf.getvalue()!r}"
        )

    @pytest.mark.parametrize("flag", ["1", None])
    def test_gated_git_op_compound_is_flag_independent(
        self, run_hook, make_event, tmp_path, flag
    ):
        repo = tmp_path / "repo"
        repo.mkdir()
        _make_repo_on_branch(repo, branch="feature-x")
        (repo / "safe.py").write_text("x = 1\n")
        cmd = f'cd {repo} && git add safe.py && echo done'
        with _env_override("GIT_SAFETY_ALLOW_COMPOUND", flag):
            result = run_hook("git-safety-guard.py", make_event("Bash", command=cmd))
        assert result.returncode == 0, f"hook must exit 0, got {result.returncode}; stderr={result.stderr!r}"
        assert result.parsed is None, (
            f"safe gated-git-op compound on a feature branch must fall through "
            f"(no hook block) regardless of flag ({flag!r}), got block: {result.stdout!r}"
        )

    def test_flag_unset_still_blocks_nongit_compound(self):
        buf = io.StringIO()
        with _env_override("GIT_SAFETY_ALLOW_COMPOUND", None):
            with contextlib.redirect_stdout(buf):
                result = self._fn()("ls | head")
        assert result is True, "flag unset must still block compounds"
        parsed = json.loads(buf.getvalue())
        assert parsed["decision"] == "block"
        assert "One command per Bash call" in parsed["reason"]

    def test_git_op_compound_still_gated_when_flag_set(self, run_hook, make_event, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _make_repo_on_branch(repo, branch="main")
        (repo / "new_file.py").write_text("x = 1\n")
        old_cwd = os.getcwd()
        os.chdir(str(repo))
        try:
            cmd = f'cd {repo} && git add new_file.py && git commit -m "feat: add x"'
            with _env_override("GIT_SAFETY_ALLOW_COMPOUND", "1"):
                result = run_hook("git-safety-guard.py", make_event("Bash", command=cmd))
            assert result.parsed is not None, (
                f"expected BLOCK for git-op compound on main, got: {result.stdout!r}"
            )
            assert result.parsed["decision"] == "block"
            assert "feature branch" in result.parsed["reason"].lower(), (
                f"git-op compound must route to branch guard, got: {result.parsed['reason']!r}"
            )
        finally:
            os.chdir(old_cwd)

    @pytest.mark.parametrize("value,blocks", [
        ("1", False), ("true", False), ("yes", False), ("on", False),
        ("TRUE", False), (" 1 ", False),
        ("0", True), ("no", True), ("off", True), ("", True),
    ])
    def test_flag_value_parsing_nongit(self, value, blocks):
        buf = io.StringIO()
        with _env_override("GIT_SAFETY_ALLOW_COMPOUND", value):
            with contextlib.redirect_stdout(buf):
                result = self._fn()("ls | head")
        assert result is blocks, (
            f"value {value!r}: expected block={blocks}, got {result}"
        )


class TestNvmBootstrapGuard:
    """nvm bootstrap is blocked (sourcing nvm dead-ends/prompts); node/npm/npx pass."""

    @pytest.mark.parametrize("command", [
        "source ~/.nvm/nvm.sh && nvm use 20",
        ". ~/.nvm/nvm.sh",
        "nvm use 20.19.6",
        "nvm install 20 && node -v",
        "export FOO=1; nvm use",
        "nvm",
    ])
    def test_blocks_nvm_bootstrap(self, command, run_hook, make_event):
        # Arrange
        event = make_event("Bash", command=command)
        # Act
        result = run_hook("git-safety-guard.py", event)
        # Assert
        assert result.parsed is not None
        assert result.parsed["decision"] == "block"
        assert "nvm" in result.parsed["reason"].lower()

    @pytest.mark.parametrize("command", [
        "node --version",
        "npm install",
        "npx tsc",
        "ls ~/.nvm",
        "cat ~/.nvm/nvm.sh",
        "which nvm",
        "echo nvm is great",
    ])
    def test_allows_non_bootstrap_node_commands(self, command, run_hook, make_event):
        # Arrange
        event = make_event("Bash", command=command)
        # Act
        result = run_hook("git-safety-guard.py", event)
        # Assert: hook must not crash AND must produce no block output.
        # returncode == 0 is load-bearing: a crashed hook also produces empty stdout
        # (the crash exits non-zero), so checking only stdout.strip() == "" is vacuous.
        assert result.returncode == 0, f"hook crashed on {command!r}: stderr={result.stderr!r}"
        assert result.stdout.strip() == ""

