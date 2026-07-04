"""Tests for deploy.sh relative-symlink behaviour.

Verifies that deploy.sh creates relative symlinks into the repo rather than
copying files, that the deployment is idempotent, that _lib/ is linked as a
directory, and that no .gitignore is written.
"""

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # tests/ -> hooks/ -> repo root
DEPLOY_SH = REPO_ROOT / "scripts" / "deploy.sh"


def run_deploy(claude_dir: Path, *, dry_run: bool = False) -> subprocess.CompletedProcess:
    """Run deploy.sh with a temp CLAUDE_DIR override."""
    cmd = ["bash", str(DEPLOY_SH)]
    if dry_run:
        cmd.append("--dry-run")
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30,
        env={
            "CLAUDE_DIR": str(claude_dir),
            "HOME": str(Path.home()),
            "PATH": "/usr/bin:/bin:/usr/local/bin:/usr/local/bin",
        },
    )


class TestDeploySymlinks:
    def test_deployed_hook_is_symlink_to_repo_source(self, tmp_path: Path):
        """After deploy, a hook in $CLAUDE_DIR/hooks/ is a symlink whose
        resolved target is the real source file under REPO_ROOT."""
        claude_dir = tmp_path / "claude_dir"
        claude_dir.mkdir()

        result = run_deploy(claude_dir)
        assert result.returncode == 0, f"deploy.sh failed:\n{result.stderr}"

        link = claude_dir / "hooks" / "git-safety-guard.py"
        assert link.exists(), f"deployed hook not found: {link}"
        assert os.path.islink(link), f"{link} must be a symlink, not a copy"

        # Resolved target must be the canonical source
        expected_src = REPO_ROOT / "hooks" / "git-safety-guard.py"
        assert link.resolve() == expected_src.resolve(), (
            f"symlink resolves to {link.resolve()}, expected {expected_src.resolve()}"
        )

    def test_symlink_target_is_relative(self, tmp_path: Path):
        """The symlink target (os.readlink) must be a relative path, not absolute."""
        claude_dir = tmp_path / "claude_dir"
        claude_dir.mkdir()

        result = run_deploy(claude_dir)
        assert result.returncode == 0, f"deploy.sh failed:\n{result.stderr}"

        link = claude_dir / "hooks" / "git-safety-guard.py"
        assert os.path.islink(link), f"{link} is not a symlink"

        target = os.readlink(link)
        assert not target.startswith("/"), (
            f"symlink target must be relative, got: {target!r}"
        )

    def test_lib_dir_reachable_through_symlink(self, tmp_path: Path):
        """$CLAUDE_DIR/hooks/_lib resolves (as a symlink or dir) and
        _lib/git.py is reachable through it."""
        claude_dir = tmp_path / "claude_dir"
        claude_dir.mkdir()

        result = run_deploy(claude_dir)
        assert result.returncode == 0, f"deploy.sh failed:\n{result.stderr}"

        lib_link = claude_dir / "hooks" / "_lib"
        # Must exist (as symlink or through symlink to a directory)
        assert lib_link.exists() or os.path.islink(lib_link), (
            f"_lib not found at {lib_link}"
        )
        assert os.path.islink(lib_link), f"_lib must be a symlink, got: {lib_link}"

        git_py = lib_link / "git.py"
        assert git_py.exists(), f"_lib/git.py not reachable through {lib_link}"

    def test_deploy_is_idempotent(self, tmp_path: Path):
        """Running deploy.sh twice leaves valid symlinks to the same targets —
        no nested or broken links."""
        claude_dir = tmp_path / "claude_dir"
        claude_dir.mkdir()

        result1 = run_deploy(claude_dir)
        assert result1.returncode == 0, f"first deploy failed:\n{result1.stderr}"

        result2 = run_deploy(claude_dir)
        assert result2.returncode == 0, f"second deploy failed:\n{result2.stderr}"

        link = claude_dir / "hooks" / "git-safety-guard.py"
        assert os.path.islink(link), f"{link} is not a symlink after second deploy"

        # Must still resolve to the correct source
        expected_src = REPO_ROOT / "hooks" / "git-safety-guard.py"
        assert link.resolve() == expected_src.resolve(), (
            f"after second deploy, symlink resolves to {link.resolve()}"
        )

        # Relative target must still be a single hop (no nesting like ../../../../...)
        target = os.readlink(link)
        assert not target.startswith("/"), "target must remain relative after re-deploy"

        # _lib must also still be a valid symlink
        lib_link = claude_dir / "hooks" / "_lib"
        assert os.path.islink(lib_link), "_lib must remain a symlink after re-deploy"
        assert (lib_link / "git.py").exists(), "_lib/git.py must still be reachable"

    def test_no_gitignore_created(self, tmp_path: Path):
        """deploy.sh must NOT create or modify any .gitignore in CLAUDE_DIR."""
        claude_dir = tmp_path / "claude_dir"
        claude_dir.mkdir()

        result = run_deploy(claude_dir)
        assert result.returncode == 0, f"deploy.sh failed:\n{result.stderr}"

        gitignore = claude_dir / ".gitignore"
        assert not gitignore.exists(), (
            "deploy.sh must not create .gitignore — gitignore-management was removed"
        )

    def test_no_gitignore_modified(self, tmp_path: Path):
        """If a .gitignore already exists, deploy.sh must not modify it."""
        claude_dir = tmp_path / "claude_dir"
        claude_dir.mkdir()

        gitignore = claude_dir / ".gitignore"
        original_content = "# My existing rules\n*.swp\n"
        gitignore.write_text(original_content)

        result = run_deploy(claude_dir)
        assert result.returncode == 0, f"deploy.sh failed:\n{result.stderr}"

        assert gitignore.read_text() == original_content, (
            "deploy.sh must not modify an existing .gitignore"
        )

    def test_readme_not_deployed_to_rules(self, tmp_path: Path):
        """deploy.sh must NOT create a symlink for rules/README.md.

        README.md is deploy meta-documentation, not a behavioral rule.
        It must never appear in the deployed CLAUDE_DIR/rules/ directory.
        """
        claude_dir = tmp_path / "claude_dir"
        claude_dir.mkdir()

        # Dry-run: README.md must not appear in dry-run output
        result = run_deploy(claude_dir, dry_run=True)
        assert result.returncode == 0, f"dry-run deploy.sh failed:\n{result.stderr}"
        assert "rules/README.md" not in result.stdout, (
            f"dry-run must not mention rules/README.md, got:\n{result.stdout}"
        )

        # Real run: README.md must not be created
        result = run_deploy(claude_dir)
        assert result.returncode == 0, f"deploy.sh failed:\n{result.stderr}"
        assert not (claude_dir / "rules" / "README.md").exists(), (
            "deploy.sh must not create ~/.claude/rules/README.md"
        )

    def test_prune_removes_orphaned_agent_symlink(self, tmp_path: Path):
        """A ct-*.md symlink whose repo source was deleted (simulating a
        removed agent) is pruned on the next deploy, while symlinks for
        agents still present in the repo are left alone."""
        claude_dir = tmp_path / "claude_dir"
        claude_dir.mkdir()

        result1 = run_deploy(claude_dir)
        assert result1.returncode == 0, f"first deploy failed:\n{result1.stderr}"

        current_agent = claude_dir / "agents" / "ct-implementer.md"
        assert current_agent.exists(), "expected ct-implementer.md to be deployed"

        # Simulate a deleted agent: a dangling symlink whose repo source
        # no longer exists.
        stale = claude_dir / "agents" / "ct-DELETED.md"
        stale.symlink_to(REPO_ROOT / "agents" / "ct-DELETED.md")
        assert os.path.islink(stale), "setup: stale symlink must exist before re-deploy"

        result2 = run_deploy(claude_dir)
        assert result2.returncode == 0, f"second deploy failed:\n{result2.stderr}"

        assert not stale.exists() and not stale.is_symlink(), (
            "stale ct-DELETED.md symlink must be pruned"
        )
        assert "pruned:" in result2.stdout, (
            f"deploy stdout must report the prune, got:\n{result2.stdout}"
        )
        assert current_agent.exists() and os.path.islink(current_agent), (
            "prune must not remove a symlink whose repo source still exists"
        )

    def test_prune_dry_run_reports_without_removing(self, tmp_path: Path):
        """--dry-run reports an orphaned agent symlink without removing it."""
        claude_dir = tmp_path / "claude_dir"
        claude_dir.mkdir()

        result1 = run_deploy(claude_dir)
        assert result1.returncode == 0, f"first deploy failed:\n{result1.stderr}"

        stale = claude_dir / "agents" / "ct-DELETED.md"
        stale.symlink_to(REPO_ROOT / "agents" / "ct-DELETED.md")

        result2 = run_deploy(claude_dir, dry_run=True)
        assert result2.returncode == 0, f"dry-run deploy failed:\n{result2.stderr}"

        assert "[dry-run] rm" in result2.stdout, (
            f"dry-run stdout must report the pending prune, got:\n{result2.stdout}"
        )
        assert stale.is_symlink(), "--dry-run must not remove the stale symlink"

    def test_prune_leaves_real_file_untouched(self, tmp_path: Path):
        """A real (non-symlink) ct-*.md file in CLAUDE_DIR with no repo
        source must never be pruned — the prune loop only ever acts on
        symlinks, per its `[[ -L "$f" ]]` guard."""
        claude_dir = tmp_path / "claude_dir"
        claude_dir.mkdir()

        result1 = run_deploy(claude_dir)
        assert result1.returncode == 0, f"first deploy failed:\n{result1.stderr}"

        real_file = claude_dir / "agents" / "ct-REAL.md"
        original_content = "# hand-authored agent note, not a repo symlink\n"
        real_file.write_text(original_content)

        result2 = run_deploy(claude_dir)
        assert result2.returncode == 0, f"second deploy failed:\n{result2.stderr}"

        assert real_file.exists() and not os.path.islink(real_file), (
            "ct-REAL.md must remain a real file, not be removed or replaced"
        )
        assert real_file.read_text() == original_content, (
            "prune must not alter the content of a real file"
        )

    def test_prune_leaves_foreign_symlink_untouched(self, tmp_path: Path):
        """A ct-*.md symlink pointing OUTSIDE this repo's agents/ dir (e.g.
        hand-placed by a user or another tool) must never be pruned, even
        though no `agents/ct-FOREIGN.md` exists in the repo — the prune
        loop only removes symlinks that resolve INTO REPO_ROOT/agents/."""
        claude_dir = tmp_path / "claude_dir"
        claude_dir.mkdir()

        result1 = run_deploy(claude_dir)
        assert result1.returncode == 0, f"first deploy failed:\n{result1.stderr}"

        foreign_target = tmp_path / "foreign-source.md"
        foreign_target.write_text("# not part of the coding-team repo\n")

        foreign = claude_dir / "agents" / "ct-FOREIGN.md"
        foreign.symlink_to(foreign_target)
        assert os.path.islink(foreign), "setup: foreign symlink must exist before re-deploy"

        result2 = run_deploy(claude_dir)
        assert result2.returncode == 0, f"second deploy failed:\n{result2.stderr}"

        assert foreign.is_symlink() and foreign.resolve() == foreign_target.resolve(), (
            "foreign ct-FOREIGN.md symlink (pointing outside REPO_ROOT/agents) "
            "must never be pruned"
        )
        assert "ct-FOREIGN.md" not in result2.stdout, (
            f"deploy stdout must not mention pruning the foreign symlink, got:\n{result2.stdout}"
        )

    def test_dry_run_creates_no_files(self, tmp_path: Path):
        """--dry-run must not create any symlinks or files in CLAUDE_DIR."""
        claude_dir = tmp_path / "claude_dir"
        claude_dir.mkdir()

        result = run_deploy(claude_dir, dry_run=True)
        assert result.returncode == 0, f"dry-run failed:\n{result.stderr}"

        # Nothing should have been created
        created = list(claude_dir.rglob("*"))
        assert not created, (
            f"--dry-run must not create any files, found: {[str(p) for p in created]}"
        )

        # Dry-run output must mention the symlink action
        assert "dry-run" in result.stdout.lower(), (
            "dry-run stdout must indicate no-op mode"
        )


class TestDeployRegistrationCheck:
    """deploy.sh's registration check greps all 5 sites, so every deployed hook
    is recognized: 'All hooks registered.' prints and no hook warns."""

    def test_all_hooks_registered_no_warnings(self, tmp_path: Path):
        claude_dir = tmp_path / "claude_dir"
        claude_dir.mkdir()
        result = run_deploy(claude_dir)
        assert result.returncode == 0, result.stderr
        assert "All hooks registered." in result.stdout, result.stdout
        assert "deployed but not registered" not in result.stdout, result.stdout


class TestPaulReviewGateSymlinks:
    def test_review_guard_symlinked(self, tmp_path: Path):
        claude_dir = tmp_path / "claude_dir"
        claude_dir.mkdir()
        result = run_deploy(claude_dir)
        assert result.returncode == 0, result.stderr
        link = claude_dir / "hooks" / "paul-apply-review-guard.py"
        assert os.path.islink(link), f"{link} must be a symlink"
        expected = REPO_ROOT / "hooks" / "paul-apply-review-guard.py"
        assert link.resolve() == expected.resolve()

    def test_agent_guard_symlinked(self, tmp_path: Path):
        claude_dir = tmp_path / "claude_dir"
        claude_dir.mkdir()
        result = run_deploy(claude_dir)
        assert result.returncode == 0, result.stderr
        link = claude_dir / "hooks" / "paul-apply-agent-guard.py"
        assert os.path.islink(link), f"{link} must be a symlink"
        expected = REPO_ROOT / "hooks" / "paul-apply-agent-guard.py"
        assert link.resolve() == expected.resolve()

    def test_paul_review_lib_reachable(self, tmp_path: Path):
        claude_dir = tmp_path / "claude_dir"
        claude_dir.mkdir()
        result = run_deploy(claude_dir)
        assert result.returncode == 0, result.stderr
        lib = claude_dir / "hooks" / "_lib"
        assert (lib / "paul_review.py").exists()
        assert (lib / "paul_review_record.py").exists()
        assert (lib / "paul_review_check.py").exists()

    def test_no_unregistered_warning_for_paul_hooks(self, tmp_path: Path):
        claude_dir = tmp_path / "claude_dir"
        claude_dir.mkdir()
        result = run_deploy(claude_dir)
        assert result.returncode == 0, result.stderr
        assert "paul-apply-review-guard.py deployed but not registered" not in result.stdout
        assert "paul-apply-agent-guard.py deployed but not registered" not in result.stdout
        assert "All hooks registered." in result.stdout, result.stdout
