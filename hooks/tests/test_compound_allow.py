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


def test_unknown_atoms_returns_unknown_atom_in_chain(settings_dir):
    cmd = "echo checking && ~/.opencode/bin/opencode --version"
    result = compound_allow.unknown_atoms(cmd, claude_dir=settings_dir)
    assert result is not None
    assert len(result) == 1
    assert "opencode --version" in result[0]

def test_unknown_atoms_empty_when_all_known(settings_dir):
    cmd = "cat file.txt | grep needle"
    assert compound_allow.unknown_atoms(cmd, claude_dir=settings_dir) == []

def test_unknown_atoms_none_for_single_command(settings_dir):
    assert compound_allow.unknown_atoms("git status", claude_dir=settings_dir) is None

def test_unknown_atoms_none_on_redirect(settings_dir):
    assert compound_allow.unknown_atoms("echo x > y.txt", claude_dir=settings_dir) is None

def test_unknown_atoms_none_on_subshell(settings_dir):
    assert compound_allow.unknown_atoms("(git status && echo done)", claude_dir=settings_dir) is None

def test_unknown_atoms_none_on_brace_group(settings_dir):
    assert compound_allow.unknown_atoms("{ echo a; echo b; }", claude_dir=settings_dir) is None

def test_unknown_atoms_none_on_nested_substitution(settings_dir):
    assert compound_allow.unknown_atoms("echo $(echo $(git rev-parse HEAD))", claude_dir=settings_dir) is None

def test_unknown_atoms_none_on_backtick(settings_dir):
    assert compound_allow.unknown_atoms("echo `git rev-parse HEAD` && echo ok", claude_dir=settings_dir) is None

def test_unknown_atoms_none_on_unbalanced_quotes(settings_dir):
    assert compound_allow.unknown_atoms('echo "open && git status', claude_dir=settings_dir) is None

def test_unknown_atoms_none_on_find_exec(settings_dir):
    assert compound_allow.unknown_atoms("find . -name x -exec rm {} ; && echo done", claude_dir=settings_dir) is None

def test_unknown_atoms_none_on_sudo(settings_dir):
    assert compound_allow.unknown_atoms("sudo apt update && echo done", claude_dir=settings_dir) is None

def test_unknown_atoms_none_when_no_allowlist(tmp_path):
    (tmp_path / "settings.json").write_text(json.dumps({"permissions": {"allow": []}}))
    compound_allow._cache.clear()
    assert compound_allow.unknown_atoms("git status && curl http://x", claude_dir=tmp_path) is None

def test_unknown_atoms_none_when_deny_mixed_with_unknown(settings_dir):
    cmd = "rm -rf /tmp/x && curl http://example"
    assert compound_allow.unknown_atoms(cmd, claude_dir=settings_dir) is None

def test_unknown_atoms_separator_only_is_none_not_empty(settings_dir):
    for cmd in [";;;", "&& ||", "|", ";", "&&"]:
        result = compound_allow.unknown_atoms(cmd, claude_dir=settings_dir)
        assert result is None, f"{cmd!r} -> {result!r}, expected None (must not be [])"

def test_unknown_atoms_never_raises_on_garbage():
    for cmd in ["", "$(", "`", ";;;", "&& ||", "$()$()", "\\", "{}", "()", "><"]:
        assert compound_allow.unknown_atoms(cmd) is None

def test_unknown_atoms_disjoint_from_auto_allow(settings_dir):
    known = "git status && echo done"
    assert compound_allow.should_auto_allow(known, claude_dir=settings_dir) is True
    assert compound_allow.unknown_atoms(known, claude_dir=settings_dir) == []
    unk = "echo hi && curl http://example"
    assert compound_allow.should_auto_allow(unk, claude_dir=settings_dir) is False
    assert compound_allow.unknown_atoms(unk, claude_dir=settings_dir)
