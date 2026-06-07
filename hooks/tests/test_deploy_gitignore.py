"""Tests for deploy.sh .gitignore block management.

Verifies that deploy.sh correctly writes and maintains a managed .gitignore
block in $CLAUDE_DIR listing all deployed artifact paths, so those derived
files are git-ignored in the claude-harness repo.
"""

import subprocess
from pathlib import Path

import pytest


SCRIPTS_DIR = Path("/Users/cevin/.claude/skills/coding-team/scripts")
DEPLOY_SH = SCRIPTS_DIR / "deploy.sh"

BEGIN_MARKER = "# BEGIN deploy-managed (coding-team deploy.sh artifacts — derived from skills/coding-team; do not edit by hand)"
END_MARKER = "# END deploy-managed"


def run_deploy(claude_dir: Path, dry_run: bool = False) -> subprocess.CompletedProcess:
    """Run deploy.sh with the given CLAUDE_DIR override."""
    cmd = ["bash", str(DEPLOY_SH)]
    if dry_run:
        cmd.append("--dry-run")
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30,
        env={"CLAUDE_DIR": str(claude_dir), "HOME": str(Path.home()), "PATH": "/usr/bin:/bin:/usr/local/bin"},
    )


def extract_block(gitignore_text: str) -> list[str]:
    """Extract lines between the BEGIN and END markers (exclusive)."""
    lines = gitignore_text.splitlines()
    in_block = False
    block_lines = []
    for line in lines:
        if line == BEGIN_MARKER:
            in_block = True
            continue
        if line == END_MARKER:
            in_block = False
            continue
        if in_block:
            block_lines.append(line)
    return block_lines


class TestDeployGitignoreBlock:
    def test_block_created_with_expected_entries(self, tmp_path: Path):
        """After deploy, .gitignore contains the managed block with key entries."""
        claude_dir = tmp_path / "claude_dir"
        claude_dir.mkdir()

        result = run_deploy(claude_dir)
        assert result.returncode == 0, f"deploy.sh failed: {result.stderr}"

        gitignore = claude_dir / ".gitignore"
        assert gitignore.exists(), ".gitignore must be created by deploy.sh"

        content = gitignore.read_text()
        assert BEGIN_MARKER in content, "BEGIN marker must be present"
        assert END_MARKER in content, "END marker must be present"

        block_lines = extract_block(content)
        assert len(block_lines) > 0, "block must contain at least one entry"

        # Both key paths must be listed
        assert "hooks/git-safety-guard.py" in block_lines, (
            "hooks/git-safety-guard.py must appear in the managed block"
        )
        assert "hooks/_lib/git.py" in block_lines, (
            "hooks/_lib/git.py must appear in the managed block"
        )

    def test_running_twice_is_idempotent(self, tmp_path: Path):
        """Running deploy.sh twice produces exactly one managed block, not two."""
        claude_dir = tmp_path / "claude_dir"
        claude_dir.mkdir()

        result1 = run_deploy(claude_dir)
        assert result1.returncode == 0, f"first deploy failed: {result1.stderr}"

        result2 = run_deploy(claude_dir)
        assert result2.returncode == 0, f"second deploy failed: {result2.stderr}"

        gitignore = claude_dir / ".gitignore"
        content = gitignore.read_text()

        # Count occurrences of the BEGIN marker — must be exactly 1
        begin_count = content.count(BEGIN_MARKER)
        assert begin_count == 1, (
            f"BEGIN marker appears {begin_count} times — must appear exactly once "
            f"(idempotency violated)"
        )

        end_count = content.count(END_MARKER)
        assert end_count == 1, (
            f"END marker appears {end_count} times — must appear exactly once"
        )

        # The block contents must be consistent after two runs
        block_lines_1 = extract_block(content)
        assert "hooks/git-safety-guard.py" in block_lines_1
        assert "hooks/_lib/git.py" in block_lines_1

    def test_content_outside_markers_preserved(self, tmp_path: Path):
        """Existing .gitignore content outside the managed block is preserved."""
        claude_dir = tmp_path / "claude_dir"
        claude_dir.mkdir()

        gitignore = claude_dir / ".gitignore"
        pre_existing = "# My existing rules\n*.swp\n.DS_Store\n"
        gitignore.write_text(pre_existing)

        result = run_deploy(claude_dir)
        assert result.returncode == 0, f"deploy.sh failed: {result.stderr}"

        content = gitignore.read_text()

        # Pre-existing content must still be present
        assert "# My existing rules" in content, (
            "pre-existing comment must be preserved outside the managed block"
        )
        assert "*.swp" in content, "*.swp must be preserved outside the managed block"
        assert ".DS_Store" in content, (
            ".DS_Store must be preserved outside the managed block"
        )

        # Block must also be present
        assert BEGIN_MARKER in content
        assert END_MARKER in content
        assert "hooks/git-safety-guard.py" in extract_block(content)

    def test_dry_run_does_not_write_gitignore(self, tmp_path: Path):
        """--dry-run prints the block to stdout but does not write .gitignore."""
        claude_dir = tmp_path / "claude_dir"
        claude_dir.mkdir()

        result = run_deploy(claude_dir, dry_run=True)
        assert result.returncode == 0, f"dry-run failed: {result.stderr}"

        gitignore = claude_dir / ".gitignore"
        assert not gitignore.exists(), (
            ".gitignore must NOT be created during --dry-run"
        )

        # But the block must appear in stdout
        assert BEGIN_MARKER in result.stdout, (
            "BEGIN marker must appear in dry-run stdout"
        )
        assert "hooks/git-safety-guard.py" in result.stdout, (
            "hooks/git-safety-guard.py must appear in dry-run stdout"
        )
        assert "hooks/_lib/git.py" in result.stdout, (
            "hooks/_lib/git.py must appear in dry-run stdout"
        )

    def test_second_deploy_updates_block_not_appends(self, tmp_path: Path):
        """After two deploys, block entries are not duplicated inside the block."""
        claude_dir = tmp_path / "claude_dir"
        claude_dir.mkdir()

        run_deploy(claude_dir)
        run_deploy(claude_dir)

        gitignore = claude_dir / ".gitignore"
        block_lines = extract_block(gitignore.read_text())

        # Each path should appear exactly once in the block
        from collections import Counter
        counts = Counter(block_lines)
        duplicates = {path: cnt for path, cnt in counts.items() if cnt > 1}
        assert not duplicates, (
            f"These paths appear multiple times in the block after two deploys: "
            f"{duplicates} — idempotency violated"
        )
