"""Unit tests for _lib/compound_allow.py — the compound auto-allow safety core.

These test the decomposition + allowlist-matching logic directly, against a
controlled settings directory, so the safety boundary is exercised without the
ambient ~/.claude allowlist.
"""

import json
import sys
from pathlib import Path

import pytest

_LIB = Path("/Users/cevin/.claude/skills/coding-team/hooks")
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from _lib import compound_allow  # noqa: E402


@pytest.fixture
def settings_dir(tmp_path):
    """A fake ~/.claude dir with a controlled Bash allow/deny list."""
    settings = {
        "permissions": {
            "allow": [
                "Bash(git *)",
                "Bash(echo *)",
                "Bash(basename *)",
                "Bash(cat *)",
                "Bash(pwd)",
            ],
            "deny": [],
        }
    }
    (tmp_path / "settings.json").write_text(json.dumps(settings))
    local = {"permissions": {"allow": ["Bash(grep *)"], "deny": ["Bash(rm *)"]}}
    (tmp_path / "settings.local.json").write_text(json.dumps(local))
    compound_allow._cache.clear()
    return tmp_path


def test_repo_root_nested_substitution_refused(settings_dir):
    cmd = 'REPO_ROOT=$(git rev-parse --show-toplevel); echo "Repo: $(basename $REPO_ROOT)"'
    assert compound_allow.should_auto_allow(cmd, claude_dir=settings_dir) is False


def test_simple_assignment_substitution_auto_allows(settings_dir):
    cmd = "REPO_ROOT=$(git rev-parse --show-toplevel); echo done"
    assert compound_allow.should_auto_allow(cmd, claude_dir=settings_dir) is True


def test_chained_allowlisted_commands_auto_allow(settings_dir):
    cmd = "git status && echo done"
    assert compound_allow.should_auto_allow(cmd, claude_dir=settings_dir) is True


def test_piped_allowlisted_commands_auto_allow(settings_dir):
    cmd = "cat file.txt | grep needle"
    assert compound_allow.should_auto_allow(cmd, claude_dir=settings_dir) is True


def test_non_allowlisted_atom_falls_through(settings_dir):
    cmd = "git status && curl http://example"
    assert compound_allow.should_auto_allow(cmd, claude_dir=settings_dir) is False


def test_deny_listed_atom_falls_through(settings_dir):
    cmd = "echo hi && rm -rf /tmp/x"
    assert compound_allow.should_auto_allow(cmd, claude_dir=settings_dir) is False


def test_plain_single_command_is_not_compound(settings_dir):
    assert compound_allow.should_auto_allow("git status", claude_dir=settings_dir) is False


def test_redirect_refused(settings_dir):
    cmd = "echo hi > /etc/passwd"
    assert compound_allow.should_auto_allow(cmd, claude_dir=settings_dir) is False


def test_nested_substitution_refused(settings_dir):
    cmd = "echo $(echo $(git rev-parse HEAD))"
    assert compound_allow.should_auto_allow(cmd, claude_dir=settings_dir) is False


def test_process_substitution_refused(settings_dir):
    cmd = "cat <(git log)"
    assert compound_allow.should_auto_allow(cmd, claude_dir=settings_dir) is False


def test_subshell_grouping_refused(settings_dir):
    cmd = "(git status && echo done)"
    assert compound_allow.should_auto_allow(cmd, claude_dir=settings_dir) is False


def test_eval_builtin_refused(settings_dir):
    settings = json.loads((settings_dir / "settings.json").read_text())
    settings["permissions"]["allow"].append("Bash(eval *)")
    (settings_dir / "settings.json").write_text(json.dumps(settings))
    compound_allow._cache.clear()
    cmd = "echo hi && eval rm -rf /"
    assert compound_allow.should_auto_allow(cmd, claude_dir=settings_dir) is False


def test_command_builtin_refused(settings_dir):
    cmd = "echo hi && command ls"
    assert compound_allow.should_auto_allow(cmd, claude_dir=settings_dir) is False


def test_unbalanced_quoting_refused(settings_dir):
    cmd = 'echo "unterminated && git status'
    assert compound_allow.should_auto_allow(cmd, claude_dir=settings_dir) is False


def test_background_job_refused(settings_dir):
    cmd = "git status & echo done"
    assert compound_allow.should_auto_allow(cmd, claude_dir=settings_dir) is False


def test_empty_allowlist_falls_through(tmp_path):
    (tmp_path / "settings.json").write_text(json.dumps({"permissions": {"allow": []}}))
    compound_allow._cache.clear()
    cmd = "git status && echo done"
    assert compound_allow.should_auto_allow(cmd, claude_dir=tmp_path) is False


def test_missing_settings_falls_through(tmp_path):
    compound_allow._cache.clear()
    cmd = "git status && echo done"
    assert compound_allow.should_auto_allow(cmd, claude_dir=tmp_path) is False


def test_decompose_strips_assignment_prefix():
    atoms = compound_allow.decompose_atoms("REPO=$(git rev-parse HEAD); echo done")
    assert atoms is not None
    assert any(a.startswith("git rev-parse") for a in atoms)
    assert any(a.startswith("echo") for a in atoms)
    assert not any(a.startswith("REPO=") for a in atoms)


def test_decompose_refuses_on_redirect():
    assert compound_allow.decompose_atoms("echo hi > out.txt") is None


def test_atom_is_allowed_deny_precedence():
    allow = frozenset(["git *", "rm *"])
    deny = frozenset(["rm *"])
    assert compound_allow.atom_is_allowed("git status", allow, deny) is True
    assert compound_allow.atom_is_allowed("rm -rf /", allow, deny) is False


def test_never_raises_on_garbage():
    for cmd in ["", "$(", "`", ";;;", "&& ||", "$()$()", "\\", "{}", "()", "><"]:
        assert compound_allow.should_auto_allow(cmd) is False
