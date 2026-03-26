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
