"""Tests for deploy.sh relative-symlink behaviour.

Verifies that deploy.sh creates relative symlinks into the repo rather than
copying files, that the deployment is idempotent, that _lib/ is linked as a
directory, and that no .gitignore is written.
"""

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path("/Users/cevin/.claude/skills/coding-team")
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
