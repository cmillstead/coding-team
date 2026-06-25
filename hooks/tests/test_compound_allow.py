"""Unit tests for _lib/compound_allow.py — the compound auto-allow safety core.

These test the decomposition + allowlist-matching logic directly, against a
controlled settings directory, so the safety boundary is exercised without the
ambient ~/.claude allowlist.
"""

import json
import sys
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parent.parent
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


def test_unknown_atoms_backtick_asymmetry_is_documented(settings_dir):
    # Intentional deviation (QA Finding 2): a backtick compound whose every atom is
    # allowlisted yields should_auto_allow True but unknown_atoms None (NOT []). Pin it
    # so the deny-flip increment cannot silently rely on the [] == all-known equivalence.
    cmd = "echo `git status` && echo done"
    assert compound_allow.should_auto_allow(cmd, claude_dir=settings_dir) is True
    assert compound_allow.unknown_atoms(cmd, claude_dir=settings_dir) is None


# ---------------------------------------------------------------------------
# Tests for is_multi_statement
# ---------------------------------------------------------------------------

class TestIsMultiStatement:
    def test_pipe(self):
        assert compound_allow.is_multi_statement("ls | wc -l") is True

    def test_and_and(self):
        assert compound_allow.is_multi_statement("a && b") is True

    def test_semicolon(self):
        assert compound_allow.is_multi_statement("cmd1; cmd2") is True

    def test_for_loop_via_semicolon(self):
        # The `;` before `do` triggers the structural signal — no keyword heuristic needed
        assert compound_allow.is_multi_statement("for f in *; do x; done") is True

    def test_command_substitution(self):
        assert compound_allow.is_multi_statement("echo $(date)") is True

    def test_heredoc(self):
        assert compound_allow.is_multi_statement("cat << EOF") is True

    def test_subshell_grouping(self):
        assert compound_allow.is_multi_statement("( cd x && y )") is True

    def test_background_ampersand(self):
        assert compound_allow.is_multi_statement("x &") is True

    def test_brace_group(self):
        assert compound_allow.is_multi_statement("{ a; b; }") is True

    def test_literal_newline(self):
        assert compound_allow.is_multi_statement("cmd1\ncmd2") is True

    def test_plain_command_false(self):
        assert compound_allow.is_multi_statement("wc -l file") is False

    def test_git_status_false(self):
        assert compound_allow.is_multi_statement("git status") is False

    def test_quoted_pipe_false(self):
        # The pipe is inside a quoted string — must not be flagged
        assert compound_allow.is_multi_statement('grep "a|b" file') is False

    def test_printf_false(self):
        assert compound_allow.is_multi_statement("printf '%s' x") is False

    def test_bare_if_as_arg_false(self):
        # `if` as a bare word argument — no `;` or newline present
        assert compound_allow.is_multi_statement("grep if file") is False

    def test_bare_for_as_arg_false(self):
        assert compound_allow.is_multi_statement("find . -name for") is False

    def test_trailing_comment_false(self):
        # `&&` and `b` are stripped by comment removal — must not be flagged
        assert compound_allow.is_multi_statement("echo ok # a && b") is False


# ---------------------------------------------------------------------------
# Tests for is_blessed_value_capture
# ---------------------------------------------------------------------------

class TestIsBlessedValueCapture:
    def test_simple_ls(self):
        assert compound_allow.is_blessed_value_capture("VAR=$(ls)") is True

    def test_git_rev_parse(self):
        assert compound_allow.is_blessed_value_capture("REPO=$(git rev-parse --show-toplevel)") is True

    def test_inner_multi_false(self):
        # Inner command is itself multi-statement — not blessed
        assert compound_allow.is_blessed_value_capture("VAR=$(ls | wc -l)") is False

    def test_trailing_after_capture_false(self):
        # Trailing `&& rm x` means the whole string is not a pure assignment
        assert compound_allow.is_blessed_value_capture("VAR=$(git status) && rm x") is False

    def test_plain_echo_false(self):
        assert compound_allow.is_blessed_value_capture("echo hi") is False


# ---------------------------------------------------------------------------
# Tests for blessed_inner_is_allowlisted
# ---------------------------------------------------------------------------

@pytest.fixture
def settings_dir_with_interpreters(tmp_path):
    """Settings dir that allowlists git, bash, python3, and node (to test interpreter hole-closure)."""
    settings = {
        "permissions": {
            "allow": [
                "Bash(git *)",
                "Bash(echo *)",
                "Bash(bash *)",
                "Bash(python3 *)",
                "Bash(node *)",
            ],
            "deny": [],
        }
    }
    (tmp_path / "settings.json").write_text(json.dumps(settings))
    compound_allow._cache.clear()
    return tmp_path


class TestBlessedInnerIsAllowlisted:
    def test_git_rev_parse_allowed(self, settings_dir):
        # REPO=$(git rev-parse --show-toplevel) — git * is allowlisted
        assert compound_allow.blessed_inner_is_allowlisted(
            "REPO=$(git rev-parse --show-toplevel)", claude_dir=settings_dir
        ) is True

    def test_unlisted_tool_false(self, settings_dir):
        # unlisted-tool is not in the allow list
        assert compound_allow.blessed_inner_is_allowlisted(
            "X=$(unlisted-tool)", claude_dir=settings_dir
        ) is False

    def test_interpreter_bash_false_even_if_allowlisted(self, settings_dir_with_interpreters):
        # CRITICAL: bash is an unsafe interpreter head — must NEVER auto-allow
        # even when `bash *` appears in the allowlist
        assert compound_allow.blessed_inner_is_allowlisted(
            "X=$(bash -lc 'a && b')", claude_dir=settings_dir_with_interpreters
        ) is False

    def test_interpreter_python3_false_even_if_allowlisted(self, settings_dir_with_interpreters):
        # python3 is an unsafe interpreter head — must NEVER auto-allow
        assert compound_allow.blessed_inner_is_allowlisted(
            "X=$(python3 -c '...')", claude_dir=settings_dir_with_interpreters
        ) is False

    def test_interpreter_node_false_even_if_allowlisted(self, settings_dir_with_interpreters):
        # node is an unsafe interpreter head — must NEVER auto-allow
        assert compound_allow.blessed_inner_is_allowlisted(
            "X=$(node -e '...')", claude_dir=settings_dir_with_interpreters
        ) is False
