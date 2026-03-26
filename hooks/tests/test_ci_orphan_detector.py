import subprocess
from pathlib import Path

HOOKS_DIR = Path("/Users/cevin/.claude/skills/coding-team/hooks")


class TestCiOrphanDetectorSyntax:
    def test_valid_bash_syntax(self):
        result = subprocess.run(
            ["bash", "-n", str(HOOKS_DIR / "ci-orphan-detector.sh")],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"


class TestCiOrphanDetectorBehavior:
    def test_exits_cleanly_with_empty_input(self):
        result = subprocess.run(
            ["bash", str(HOOKS_DIR / "ci-orphan-detector.sh")],
            input="", capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0

    def test_exits_cleanly_when_gh_not_available(self):
        # Provide a PATH that includes bash but NOT gh
        result = subprocess.run(
            ["bash", str(HOOKS_DIR / "ci-orphan-detector.sh")],
            input="", capture_output=True, text=True, timeout=15,
            env={"PATH": "/bin:/usr/bin"},
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""


class TestStaleBranchDetection:
    def test_stale_branch_section_exists(self):
        """Verify the script contains stale branch detection code."""
        script = (HOOKS_DIR / "ci-orphan-detector.sh").read_text()
        assert "Stale branch detection" in script
        assert "stale_lines" in script
        assert "cutoff" in script
        assert "git branch" in script
        # Verify the bash syntax is still valid after adding stale branch code
        result = subprocess.run(
            ["bash", "-n", str(HOOKS_DIR / "ci-orphan-detector.sh")],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_script_syntax_valid(self):
        """Run bash -n to verify no syntax errors in the complete script."""
        result = subprocess.run(
            ["bash", "-n", str(HOOKS_DIR / "ci-orphan-detector.sh")],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"
        assert result.stderr.strip() == "", f"Unexpected warnings: {result.stderr}"
