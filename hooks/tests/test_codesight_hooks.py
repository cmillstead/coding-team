"""Tests for codesight-hooks.py hook."""

import importlib.util
import json
import os
import subprocess
import sys
import types
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent.parent  # tests/ -> hooks/
CODESIGHT_HOOKS = HOOKS_DIR / "codesight-hooks.py"


def _run_agent_hook(event, *, home=None, cwd=None):
    """Run codesight-hooks.py as a subprocess with optional HOME/cwd override.
    Returns a namespace with .parsed/.stdout/.stderr/.returncode so tests use
    result.parsed like the existing run_hook fixture."""
    env = {**os.environ}
    if home is not None:
        env["HOME"] = str(home)
    cp = subprocess.run(
        [sys.executable, str(CODESIGHT_HOOKS)],
        input=json.dumps(event), capture_output=True, text=True,
        timeout=10, env=env, cwd=(str(cwd) if cwd else None),
    )
    try:
        parsed = json.loads(cp.stdout)
    except (json.JSONDecodeError, ValueError):
        parsed = None
    return types.SimpleNamespace(stdout=cp.stdout, stderr=cp.stderr,
                                 returncode=cp.returncode, parsed=parsed)


class TestPreToolUseAgentEdgeCases:
    def test_non_string_prompt_no_crash(self, run_hook):
        # Build event manually: prompt is a list (non-string truthy value).
        # make_event can't inject a non-string prompt because it guards on the
        # string value — construct the event dict directly.
        event = {"tool_name": "Agent", "tool_input": {"prompt": ["a list"]}}
        result = run_hook("codesight-hooks.py", event)
        assert result.returncode == 0
        # Guard must return without output — no crash, no hookSpecificOutput
        assert result.stdout.strip() == ""


class TestPreToolUseAgent:
    def test_injects_codesight_instruction_into_agent_prompt(self, make_event, tmp_path):
        proj = tmp_path / "src" / "proj"
        proj.mkdir(parents=True)
        event = make_event("Agent", prompt="Search for the function definition")
        result = _run_agent_hook(event, home=tmp_path, cwd=proj)
        assert result.parsed is not None
        # Should have hookSpecificOutput with updatedInput
        hook_output = result.parsed.get("hookSpecificOutput", {})
        updated = hook_output.get("updatedInput", {})
        assert "codesight" in updated.get("prompt", "").lower()
        assert "mcp__codesight__query" in updated.get("prompt", "")


class TestPostToolUseWrite:
    def test_no_output_for_non_src_path(self, run_hook, make_event):
        event = make_event(
            "Write",
            file_path="/tmp/some-file.txt",
            content="hello",
            tool_result="File written",
        )
        result = run_hook("codesight-hooks.py", event)
        # PostToolUse Write to non-~/src/ path should produce no output
        assert result.stdout.strip() == ""


class TestStyleInjection:
    def test_code_work_prompt_gets_style_injection(self, run_hook, make_event):
        """Agent prompt with code work signals gets style instruction appended."""
        event = make_event("Agent", prompt="Implement the login feature")
        result = run_hook("codesight-hooks.py", event)
        assert result.parsed is not None
        output = result.parsed.get("hookSpecificOutput", {})
        updated = output.get("updatedInput", {}).get("prompt", "")
        assert "code-style.md" in updated
        assert "golden-principles.md" in updated

    def test_non_code_prompt_no_style_injection(self, make_event, tmp_path):
        """Agent prompt without code signals does not get style injection."""
        proj = tmp_path / "src" / "proj"
        proj.mkdir(parents=True)
        event = make_event("Agent", prompt="Summarize the meeting notes")
        result = _run_agent_hook(event, home=tmp_path, cwd=proj)
        assert result.parsed is not None
        output = result.parsed.get("hookSpecificOutput", {})
        updated = output.get("updatedInput", {}).get("prompt", "")
        assert "MANDATORY SEARCH RULES" in updated  # codesight still injected
        assert "code-style.md" not in updated

    def test_design_prompt_gets_style_injection(self, run_hook, make_event):
        """Agent prompt with design/architecture signals gets style injection."""
        event = make_event("Agent", prompt="Design the database schema architecture")
        result = run_hook("codesight-hooks.py", event)
        assert result.parsed is not None
        output = result.parsed.get("hookSpecificOutput", {})
        updated = output.get("updatedInput", {}).get("prompt", "")
        assert "golden-principles.md" in updated


class TestNonAgentTool:
    def test_no_output_for_bash(self, run_hook, make_event):
        event = make_event("Bash", command="ls -la")
        result = run_hook("codesight-hooks.py", event)
        assert result.stdout.strip() == ""

    def test_no_output_for_read(self, run_hook, make_event):
        event = make_event("Read", file_path="/tmp/file.py")
        result = run_hook("codesight-hooks.py", event)
        assert result.stdout.strip() == ""


class TestFieldPreservation:
    """Regression: the merge must preserve non-prompt Agent fields (e.g. description).

    A prior bug emitted updatedInput={"prompt": ...} only, stripping the Agent
    tool's required `description` and causing every dispatch to fail schema
    validation. See update_input merge contract in _lib/output.py.
    """

    def test_preserves_other_agent_fields(self, make_event, tmp_path):
        proj = tmp_path / "src" / "proj"
        proj.mkdir(parents=True)
        event = make_event(
            "Agent",
            prompt="Search for the function definition",
            description="my subagent task",
            subagent_type="Explore",
            model="sonnet",
        )
        result = _run_agent_hook(event, home=tmp_path, cwd=proj)
        assert result.parsed is not None
        updated = result.parsed["hookSpecificOutput"]["updatedInput"]
        # Non-prompt fields survive the merge
        assert updated["description"] == "my subagent task"
        assert updated["subagent_type"] == "Explore"
        assert updated["model"] == "sonnet"
        # Prompt is still augmented with the injection
        assert "MANDATORY SEARCH RULES" in updated["prompt"]
        assert updated["prompt"].startswith("Search for the function definition")


class TestHandlePostQuery:
    """Tests for handle_post_query: mcp__codesight__query PostToolUse → TSV usage log.

    Runs the hook as a subprocess with HOME set to a tmp dir so the usage log
    resolves under tmp (HOME/.config/codesight-mcp/usage.log), keeping the real
    usage log unmodified.
    """

    def _run_hook(self, event: dict, tmp_home: Path) -> subprocess.CompletedProcess:
        env = {**os.environ, "HOME": str(tmp_home)}
        return subprocess.run(
            [sys.executable, str(CODESIGHT_HOOKS)],
            input=json.dumps(event),
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

    def _usage_log(self, tmp_home: Path) -> Path:
        return tmp_home / ".config" / "codesight-mcp" / "usage.log"

    def _last_tsv_fields(self, tmp_home: Path) -> list[str]:
        return self._usage_log(tmp_home).read_text().splitlines()[-1].split("\t")

    def test_ok_status_appends_tsv_line(self, tmp_path):
        """Successful query appends a 5-field TSV line with status=ok."""
        event = {
            "tool_name": "mcp__codesight__query",
            "tool_input": {
                "operation": "search-symbols",
                "params": {"repo": "test-repo", "query": "dispatcher"},
            },
            "tool_result": {"success": True},
        }
        result = self._run_hook(event, tmp_path)
        assert result.returncode == 0
        fields = self._last_tsv_fields(tmp_path)
        assert len(fields) == 5, f"Expected 5 TSV fields, got {len(fields)}: {fields}"
        assert fields[1] == "search-symbols"
        assert fields[2] == "test-repo"
        assert fields[3] == "dispatcher"
        assert fields[4] == "ok"

    def test_error_status_appends_tsv_line(self, tmp_path):
        """Query with is_error in tool_result appends a TSV line with status=error."""
        event = {
            "tool_name": "mcp__codesight__query",
            "tool_input": {
                "operation": "get-symbol",
                "params": {"repo": "my-repo", "query": "some_func"},
            },
            "tool_result": {"is_error": True, "content": "Error: not found"},
        }
        result = self._run_hook(event, tmp_path)
        assert result.returncode == 0
        fields = self._last_tsv_fields(tmp_path)
        assert len(fields) == 5, f"Expected 5 TSV fields, got {len(fields)}: {fields}"
        assert fields[1] == "get-symbol"
        assert fields[4] == "error"

    def test_symbol_id_fallback_for_query_column(self, tmp_path):
        """When params has symbol_id but no query, symbol_id is used for the query column."""
        event = {
            "tool_name": "mcp__codesight__query",
            "tool_input": {
                "operation": "get-symbol",
                "params": {"repo": "my-repo", "symbol_id": "MyClass.my_method"},
            },
            "tool_result": {"success": True},
        }
        result = self._run_hook(event, tmp_path)
        assert result.returncode == 0
        fields = self._last_tsv_fields(tmp_path)
        assert len(fields) == 5, f"Expected 5 TSV fields, got {len(fields)}: {fields}"
        assert fields[3] == "MyClass.my_method"


def _load_module():
    """Load the hyphen-named codesight-hooks.py in-process for unit tests."""
    spec = importlib.util.spec_from_file_location("codesight_hooks", CODESIGHT_HOOKS)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestCodesightPathGate:
    """The MANDATORY-codesight directive is injected only when cwd is under ~/src/.

    codesight-mcp only indexes repos under ~/src/, so the directive is an
    unfollowable order anywhere else. The STYLE directive is orthogonal and
    must still fire on code-work prompts regardless of cwd.
    """

    def test_pre_agent_injects_codesight_inside_src(self, make_event, tmp_path):
        proj = tmp_path / "src" / "proj"
        proj.mkdir(parents=True)
        event = make_event("Agent", prompt="find the function")
        result = _run_agent_hook(event, home=tmp_path, cwd=proj)
        assert result.parsed is not None
        updated = result.parsed["hookSpecificOutput"]["updatedInput"]["prompt"]
        assert "MANDATORY SEARCH RULES" in updated

    def test_pre_agent_omits_codesight_outside_src(self, make_event, tmp_path):
        event = make_event("Agent", prompt="find the function")
        result = _run_agent_hook(event, home=tmp_path, cwd=tmp_path)
        assert result.parsed is not None
        updated = result.parsed["hookSpecificOutput"]["updatedInput"]["prompt"]
        assert "MANDATORY SEARCH RULES" not in updated

    def test_pre_agent_style_present_outside_src(self, make_event, tmp_path):
        event = make_event("Agent", prompt="implement the login feature")
        result = _run_agent_hook(event, home=tmp_path, cwd=tmp_path)
        assert result.parsed is not None
        updated = result.parsed["hookSpecificOutput"]["updatedInput"]["prompt"]
        assert "code-style.md" in updated

    def test_pre_agent_omits_codesight_for_sibling_srcfoo(self, make_event, tmp_path):
        (tmp_path / "src").mkdir()
        proj = tmp_path / "srcfoo" / "proj"
        proj.mkdir(parents=True)
        event = make_event("Agent", prompt="find the function")
        result = _run_agent_hook(event, home=tmp_path, cwd=proj)
        assert result.parsed is not None
        updated = result.parsed["hookSpecificOutput"]["updatedInput"]["prompt"]
        assert "MANDATORY SEARCH RULES" not in updated

    def test_pre_agent_empty_prompt_unchanged(self):
        event = {"tool_name": "Agent", "tool_input": {"prompt": ""}}
        result = _run_agent_hook(event)
        assert result.stdout.strip() == ""
        assert result.stderr == ""

    def test_codesight_covers_cwd_false_on_getcwd_oserror(self, tmp_path):
        """A deleted cwd makes os.getcwd() raise a real OSError; the guard must
        swallow it and return False (fail off — do not inject the directive)."""
        mod = _load_module()
        gone = tmp_path / "gone"
        gone.mkdir()
        orig = os.getcwd()
        os.chdir(gone)
        try:
            gone.rmdir()  # cwd now deleted -> os.getcwd() raises OSError
            assert mod.codesight_covers_cwd() is False
        finally:
            os.chdir(orig)
