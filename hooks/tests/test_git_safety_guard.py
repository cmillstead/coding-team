"""Tests for git-safety-guard.py hook."""


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
