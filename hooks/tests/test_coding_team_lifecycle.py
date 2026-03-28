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
        """PostToolUse cleanup runs when second-opinion gate passes."""
        # Create active file + declined marker so the gate passes
        code = (
            "import sys, json, os, io, time, runpy\n"
            f"sys.path.insert(0, {str(HOOKS_DIR)!r})\n"
            "with open('/tmp/coding-team-active', 'w') as _f:\n"
            "    _f.write(str(time.time()))\n"
            "with open('/tmp/second-opinion-declined', 'w') as _f:\n"
            "    _f.write('skipped')\n"
        )
        hook_path = str(HOOKS_DIR / "coding-team-lifecycle.py")
        code += f"runpy.run_path({hook_path!r}, run_name='__main__')\n"

        event = {"tool_name": "Skill", "tool_input": {"skill": "coding-team"},
                 "tool_result": "done"}
        result = subprocess.run(
            ["python3", "-c", code],
            input=json.dumps(event),
            capture_output=True,
            text=True,
            timeout=10,
        )
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


class TestPostToolUseCleanup:
    """PostToolUse for coding-team cleans up all marker files."""

    def test_removes_second_opinion_marker_on_post(self):
        """Second-opinion completion marker is cleaned up when pipeline ends."""
        so_marker = "/tmp/second-opinion-completed"
        # Create both the active file and second-opinion marker atomically
        code = (
            "import sys, json, os, io, time, runpy\n"
            f"sys.path.insert(0, {str(HOOKS_DIR)!r})\n"
            "with open('/tmp/coding-team-active', 'w') as _f:\n"
            "    _f.write(str(time.time()))\n"
            "with open('/tmp/second-opinion-completed', 'w') as _f:\n"
            "    _f.write('done')\n"
        )
        hook_path = str(HOOKS_DIR / "coding-team-lifecycle.py")
        code += f"runpy.run_path({hook_path!r}, run_name='__main__')\n"

        event = {"tool_name": "Skill", "tool_input": {"skill": "coding-team"},
                 "tool_result": "done"}
        result = subprocess.run(
            ["python3", "-c", code],
            input=json.dumps(event),
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert not os.path.exists(so_marker)
        assert not os.path.exists(ACTIVE_FILE)


class TestSecondOpinionGate:
    """PostToolUse for coding-team blocks completion unless second-opinion was addressed.

    Fail-closed: if neither /tmp/second-opinion-completed nor /tmp/second-opinion-declined
    exists, the hook blocks pipeline completion. This is structural enforcement — the LLM
    cannot rationalize past it.
    """

    SO_COMPLETED = "/tmp/second-opinion-completed"
    SO_DECLINED = "/tmp/second-opinion-declined"

    def _run_post_with_markers(self, completed=False, declined=False):
        """Run PostToolUse for coding-team with optional markers, atomically."""
        code = (
            "import sys, json, os, io, time, runpy\n"
            f"sys.path.insert(0, {str(HOOKS_DIR)!r})\n"
            "with open('/tmp/coding-team-active', 'w') as _f:\n"
            "    _f.write(str(time.time()))\n"
        )
        if completed:
            code += (
                "with open('/tmp/second-opinion-completed', 'w') as _f:\n"
                "    _f.write('done')\n"
            )
        if declined:
            code += (
                "with open('/tmp/second-opinion-declined', 'w') as _f:\n"
                "    _f.write('skipped')\n"
            )
        hook_path = str(HOOKS_DIR / "coding-team-lifecycle.py")
        code += f"runpy.run_path({hook_path!r}, run_name='__main__')\n"

        event = {"tool_name": "Skill", "tool_input": {"skill": "coding-team"},
                 "tool_result": "done"}
        return subprocess.run(
            ["python3", "-c", code],
            input=json.dumps(event),
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_blocks_when_neither_marker_exists(self):
        """Fail-closed: no markers → block completion."""
        result = self._run_post_with_markers(completed=False, declined=False)
        assert result.returncode == 0
        parsed = json.loads(result.stdout)
        assert parsed["decision"] == "block"
        assert "second-opinion" in parsed["reason"].lower()

    def test_allows_when_completed_marker_exists(self):
        """User ran codex → allow completion."""
        result = self._run_post_with_markers(completed=True)
        assert result.returncode == 0
        # Should produce no block output (silent allow + cleanup)
        stdout = result.stdout.strip()
        if stdout:
            parsed = json.loads(stdout)
            assert parsed.get("decision") != "block"

    def test_allows_when_declined_marker_exists(self):
        """User explicitly declined → allow completion."""
        result = self._run_post_with_markers(declined=True)
        assert result.returncode == 0
        stdout = result.stdout.strip()
        if stdout:
            parsed = json.loads(stdout)
            assert parsed.get("decision") != "block"

    def test_cleans_up_completed_marker_after_gate_passes(self):
        """Markers are cleaned up when the pipeline completes."""
        self._run_post_with_markers(completed=True)
        assert not os.path.exists(self.SO_COMPLETED)
        assert not os.path.exists(ACTIVE_FILE)

    def test_cleans_up_declined_marker_after_gate_passes(self):
        """Declined marker is cleaned up when the pipeline completes."""
        self._run_post_with_markers(declined=True)
        assert not os.path.exists(self.SO_DECLINED)
        assert not os.path.exists(ACTIVE_FILE)

    def test_cleans_up_both_markers_after_gate_passes(self):
        """Both markers cleaned up when both exist."""
        self._run_post_with_markers(completed=True, declined=True)
        assert not os.path.exists(self.SO_COMPLETED)
        assert not os.path.exists(self.SO_DECLINED)
        assert not os.path.exists(ACTIVE_FILE)


class TestNonCodingTeamSkill:
    def test_allows_silently_for_other_skills(self, run_hook, make_event):
        event = make_event("Skill", skill="some-other-skill")
        result = run_hook("coding-team-lifecycle.py", event)
        assert result.returncode == 0
        # No output means silent allow
        assert result.stdout.strip() == ""
