import subprocess
from pathlib import Path

HOOKS_DIR = Path("/Users/cevin/.claude/skills/coding-team/hooks")


class TestQmdVaultEmbedSyntax:
    def test_valid_bash_syntax(self):
        result = subprocess.run(
            ["bash", "-n", str(HOOKS_DIR / "qmd-vault-embed.sh")],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"


class TestQmdVaultEmbedBehavior:
    def test_exits_cleanly_when_path_not_in_obsidian_vault(self):
        payload = '{"tool_input":{"file_path":"/tmp/some-other-file.md"}}'
        result = subprocess.run(
            ["bash", str(HOOKS_DIR / "qmd-vault-embed.sh")],
            input=payload, capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0

    def test_exits_cleanly_when_path_in_obsidian_vault(self):
        payload = '{"tool_input":{"file_path":"/Users/cevin/Documents/obsidian-vault/test.md"}}'
        result = subprocess.run(
            ["bash", str(HOOKS_DIR / "qmd-vault-embed.sh")],
            input=payload, capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0

    def test_handles_empty_input_gracefully(self):
        result = subprocess.run(
            ["bash", str(HOOKS_DIR / "qmd-vault-embed.sh")],
            input="", capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0
