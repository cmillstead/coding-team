"""Tests for ask-first-gate.py hook."""


class TestBashDependencyPatterns:
    def test_npm_install_triggers_dependency_advisory(self, run_hook, make_event):
        event = make_event("Bash", command="npm install lodash")
        result = run_hook("ask-first-gate.py", event)
        assert result.parsed is not None
        assert result.parsed["decision"] == "allow"
        assert "dependency" in result.parsed["reason"].lower()

    def test_yarn_add_triggers_dependency_advisory(self, run_hook, make_event):
        event = make_event("Bash", command="yarn add react")
        result = run_hook("ask-first-gate.py", event)
        assert result.parsed is not None
        assert result.parsed["decision"] == "allow"
        assert "dependency" in result.parsed["reason"].lower()

    def test_pip_install_triggers_dependency_advisory(self, run_hook, make_event):
        event = make_event("Bash", command="pip install requests")
        result = run_hook("ask-first-gate.py", event)
        assert result.parsed is not None
        assert result.parsed["decision"] == "allow"
        assert "dependency" in result.parsed["reason"].lower()


class TestBashMigrationPatterns:
    def test_makemigrations_triggers_migration_advisory(self, run_hook, make_event):
        event = make_event("Bash", command="python manage.py makemigrations")
        result = run_hook("ask-first-gate.py", event)
        assert result.parsed is not None
        assert result.parsed["decision"] == "allow"
        assert "migration" in result.parsed["reason"].lower()


class TestBashNoMatch:
    def test_ls_produces_no_output(self, run_hook, make_event):
        event = make_event("Bash", command="ls -la")
        result = run_hook("ask-first-gate.py", event)
        assert result.stdout.strip() == ""

    def test_git_status_produces_no_output(self, run_hook, make_event):
        event = make_event("Bash", command="git status")
        result = run_hook("ask-first-gate.py", event)
        assert result.stdout.strip() == ""


class TestEditDependencyManifest:
    def test_edit_package_json_triggers_advisory(self, run_hook, make_event):
        event = make_event("Edit", file_path="/project/package.json")
        result = run_hook("ask-first-gate.py", event)
        assert result.parsed is not None
        assert result.parsed["decision"] == "allow"
        assert "dependency" in result.parsed["reason"].lower() or "package.json" in result.parsed["reason"]

    def test_edit_normal_file_no_output(self, run_hook, make_event):
        event = make_event("Edit", file_path="/project/src/main.py")
        result = run_hook("ask-first-gate.py", event)
        assert result.stdout.strip() == ""


class TestWriteDependencyManifest:
    def test_write_requirements_txt_triggers_advisory(self, run_hook, make_event):
        event = make_event("Write", file_path="/project/requirements.txt", content="requests==2.31.0")
        result = run_hook("ask-first-gate.py", event)
        assert result.parsed is not None
        assert result.parsed["decision"] == "allow"
        assert "dependency" in result.parsed["reason"].lower() or "requirements.txt" in result.parsed["reason"]


class TestNonMatchingTool:
    def test_read_tool_produces_no_output(self, run_hook, make_event):
        event = make_event("Read", file_path="/project/src/main.py")
        result = run_hook("ask-first-gate.py", event)
        assert result.stdout.strip() == ""
