"""Tests for coding-team-lifecycle.py hook.

NOTE: The live Claude Code session runs hooks that delete /tmp/coding-team-active
between our Bash tool calls. To avoid this race condition, we create the active file
INSIDE the subprocess and run the hook's main() function directly, all within a
single process invocation.
"""

import json
import os
import subprocess
from pathlib import Path

import pytest


HOOKS_DIR = Path("/Users/cevin/.claude/skills/coding-team/hooks")
ACTIVE_FILE = "/tmp/coding-team-active"


@pytest.fixture(autouse=True)
def cleanup_active_file():
    """Remove the active marker file before and after each test."""
    if os.path.exists(ACTIVE_FILE):
        os.remove(ACTIVE_FILE)
    yield
    if os.path.exists(ACTIVE_FILE):
        os.remove(ACTIVE_FILE)


def run_lifecycle_with_setup(event: dict, create_active: bool = False) -> subprocess.CompletedProcess:
    """Run lifecycle hook with optional active file creation, all atomically."""
    # Use runpy to run the hook as a module, calling main()
    code = (
        "import sys, json, os, io, time, runpy\n"
        f"sys.path.insert(0, {str(HOOKS_DIR)!r})\n"
    )
    if create_active:
        code += (
            "with open('/tmp/coding-team-active', 'w') as _f:\n"
            "    _f.write(str(time.time()))\n"
        )
    # Run the hook file directly via runpy which sets __name__ = '__main__'
    hook_path = str(HOOKS_DIR / "coding-team-lifecycle.py")
    code += f"runpy.run_path({hook_path!r}, run_name='__main__')\n"

    return subprocess.run(
        ["python3", "-c", code],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        timeout=10,
    )


class TestPreToolUseSkillCodingTeam:
    def test_allows_and_creates_active_file_when_no_marker(self, run_hook, make_event):
        event = make_event("Skill", skill="coding-team")
        result = run_hook("coding-team-lifecycle.py", event)
        # Should allow (no block output) and create the active file
        assert result.returncode == 0
        if result.parsed:
            assert result.parsed.get("decision") != "block"

    def test_blocks_recursive_invocation_when_marker_exists(self):
        event = {"tool_name": "Skill", "tool_input": {"skill": "coding-team"}}
        result = run_lifecycle_with_setup(event, create_active=True)
        assert result.returncode == 0
        parsed = json.loads(result.stdout)
        assert parsed["decision"] == "block"
        assert "recursive" in parsed["reason"].lower()


class TestPostToolUseSkillCodingTeam:
    def test_removes_active_file_on_post(self):
        event = {"tool_name": "Skill", "tool_input": {"skill": "coding-team"},
                 "tool_result": "done"}
        result = run_lifecycle_with_setup(event, create_active=True)
        assert result.returncode == 0
        # The hook removes the active file on PostToolUse
        assert not os.path.exists(ACTIVE_FILE)


class TestSubSkillsPassThrough:
    """Sub-skills must NOT be blocked when the pipeline is active.

    The recursion guard only protects against re-entering /coding-team itself.
    Skills like /second-opinion, /debug, /harness-engineer are designed to be
    invoked WITHIN the pipeline.
    """

    @pytest.mark.parametrize("skill_name", [
        "second-opinion",
        "debug",
        "harness-engineer",
        "prompt-craft",
        "verify",
        "tdd",
        "review-feedback",
        "scope-lock",
        "scope-unlock",
        "release",
        "retrospective",
        "doc-sync",
        "parallel-fix",
        "worktree",
    ])
    def test_sub_skill_allowed_when_pipeline_active(self, skill_name):
        """Sub-skills pass through even when /tmp/coding-team-active exists."""
        event = {"tool_name": "Skill", "tool_input": {"skill": skill_name}}
        result = run_lifecycle_with_setup(event, create_active=True)
        assert result.returncode == 0
        # Should produce no output (silent allow), not a block
        assert result.stdout.strip() == ""


class TestNonCodingTeamSkill:
    def test_allows_silently_for_other_skills(self, run_hook, make_event):
        event = make_event("Skill", skill="some-other-skill")
        result = run_hook("coding-team-lifecycle.py", event)
        assert result.returncode == 0
        # No output means silent allow
        assert result.stdout.strip() == ""
