"""Unit tests for _lib/compound_allow.py — the compound command detection core.

After the value-capture auto-allow removal, this module only provides two
public functions:

  * is_multi_statement — detects multi-statement shell compounds (for blocking)
  * is_blessed_value_capture — detects VAR=$(single) captures (for fall-through
    to prompt instead of block)

All settings/allowlist machinery (get_bash_rules, atom_is_allowed,
decompose_atoms, blessed_inner_is_allowlisted, _BLESS_SAFE_HEADS, etc.) has
been deleted. Tests for those deleted functions have been removed here.
"""

import sys
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parent.parent
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from _lib import compound_allow  # noqa: E402


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

    # --- fd-duplication / combined redirect cases (must be False) ---

    def test_redirect_2_gt_1_false(self):
        # 2>&1 is a redirect, not a background job or connector
        assert compound_allow.is_multi_statement("cmd 2>&1") is False

    def test_redirect_cmd_log_2_gt_1_false(self):
        # cmd >log 2>&1 is a single command with output + stderr redirect
        assert compound_allow.is_multi_statement("cmd >log 2>&1") is False

    def test_redirect_gt_2_false(self):
        # >&2 redirects stdout to stderr — single command
        assert compound_allow.is_multi_statement("ls >&2") is False

    def test_redirect_amp_gt_file_false(self):
        # &>file combines stdout+stderr redirect — still a single command
        assert compound_allow.is_multi_statement("echo hi &>out.txt") is False

    def test_redirect_2_gt_dash_false(self):
        # 2>&- closes stderr fd — single command
        assert compound_allow.is_multi_statement("cmd 2>&-") is False

    def test_redirect_lt_amp_3_false(self):
        # <&3 duplicates fd 3 to stdin — single command
        assert compound_allow.is_multi_statement("cmd <&3") is False

    def test_redirect_1_gt_2_false(self):
        # 1>&2 redirects stdout to stderr — single command
        assert compound_allow.is_multi_statement("git rev-parse 1>&2") is False

    # --- real background / connectors (must still be True) ---

    def test_background_cmd_amp_true(self):
        # trailing & puts the command in background — compound
        assert compound_allow.is_multi_statement("cmd &") is True

    def test_background_a_amp_b_true(self):
        # a & b is two processes — compound
        assert compound_allow.is_multi_statement("a & b") is True

    def test_background_and_and_still_true(self):
        # && is a logical-AND chain — must still be caught
        assert compound_allow.is_multi_statement("a && b") is True

    def test_background_sleep_amp_true(self):
        # sleep 5 & — detach to background
        assert compound_allow.is_multi_statement("sleep 5 &") is True


# ---------------------------------------------------------------------------
# Tests for is_blessed_value_capture
# ---------------------------------------------------------------------------

class TestIsBlessedValueCapture:
    def test_simple_ls(self):
        assert compound_allow.is_blessed_value_capture("VAR=$(ls)") is True

    def test_git_rev_parse(self):
        assert compound_allow.is_blessed_value_capture("REPO=$(git rev-parse --show-toplevel)") is True

    def test_npm_inner(self):
        # npm value-captures are now blessed (shape check only, no allowlist gate)
        assert compound_allow.is_blessed_value_capture("X=$(npm root)") is True

    def test_bash_inner_with_single_arg(self):
        # bash with a simple arg has no nested substitution — blessed by shape
        assert compound_allow.is_blessed_value_capture("X=$(bash --version)") is True

    def test_inner_multi_false(self):
        # Inner command is itself multi-statement — not blessed
        assert compound_allow.is_blessed_value_capture("VAR=$(ls | wc -l)") is False

    def test_trailing_after_capture_false(self):
        # Trailing `&& rm x` means the whole string is not a pure assignment
        assert compound_allow.is_blessed_value_capture("VAR=$(git status) && rm x") is False

    def test_plain_echo_false(self):
        assert compound_allow.is_blessed_value_capture("echo hi") is False

    def test_value_capture_with_trailing_comment_false(self):
        """VAR=$(git status) # comment is NOT a blessed capture.

        A trailing comment after the closing ``)`` means the whole string does
        not match the pure ``VAR=$(...)`` pattern — the comment text trails
        outside the capture, so _BLESSED_CAPTURE does not match. This is the
        correct/safe behavior: a comment can disguise a payload.
        """
        assert compound_allow.is_blessed_value_capture("VAR=$(git status) # comment") is False

    def test_interpreter_capture_single_inner_blessed(self):
        """X=$(bash -lc 'cmd') — inner has no nested substitution.

        Note: 'bash -lc 'cmd'' is tokenized so the inner command is
        `bash -lc cmd` (quotes stripped). is_multi_statement on that is False.
        So this IS a blessed shape. The hook lets it PROMPT (not auto-allow).
        """
        # The inner command "bash -lc 'cmd'" strips quotes to "bash -lc cmd"
        # which is a single statement — blessed by shape.
        assert compound_allow.is_blessed_value_capture("X=$(bash -lc 'cmd')") is True

    def test_interpreter_capture_unquoted_compound_inner_not_blessed(self):
        """X=$(bash -lc a && b) — inner has unquoted && after quote strip — NOT blessed."""
        # The inner command 'bash -lc a && b' (no quotes around 'a && b') contains
        # unquoted && — is_multi_statement returns True — NOT blessed.
        assert compound_allow.is_blessed_value_capture("X=$(bash -lc a && b)") is False


# ---------------------------------------------------------------------------
# Tests for is_multi_statement — capture-with-comment edge case
# ---------------------------------------------------------------------------


class TestCaptureWithCommentEdge:
    """Document the capture-with-comment edge: VAR=$(cmd) # comment is BLOCKED.

    is_blessed_value_capture returns False (trailing comment defeats blessing),
    AND is_multi_statement returns True (the $( signal is present).
    Together they ensure the command is blocked rather than falling through.
    """

    def test_capture_with_comment_is_not_blessed(self):
        """A trailing comment defeats blessed value-capture recognition."""
        assert compound_allow.is_blessed_value_capture("VAR=$(git status) # comment") is False

    def test_capture_with_comment_is_multi_statement(self):
        """A trailing comment does NOT suppress the $( signal in is_multi_statement.

        The comment stripper removes ``# comment`` (and everything after it), but
        ``$(`` appears BEFORE the comment, so it survives into the preprocessed
        string and triggers the multi-statement check.
        """
        assert compound_allow.is_multi_statement("VAR=$(git status) # comment") is True


# ---------------------------------------------------------------------------
# P2 tests: is_multi_statement trailing `;` false-deny fix
# ---------------------------------------------------------------------------

class TestTrailingSemicolon:
    """P2: a trailing `;` on an otherwise-single command must not trigger multi-statement."""

    def test_echo_trailing_semicolon_false(self):
        # `echo hi;` is functionally a single command — must not be flagged
        assert compound_allow.is_multi_statement("echo hi;") is False

    def test_echo_trailing_semicolon_comment_false(self):
        # `echo hi; # comment` — trailing `;` before comment; still single
        assert compound_allow.is_multi_statement("echo hi; # comment") is False

    def test_ls_space_semicolon_false(self):
        # `ls ;` — trailing `;` with leading whitespace; still single
        assert compound_allow.is_multi_statement("ls ;") is False

    def test_two_commands_semicolon_true(self):
        # `a; b` — non-terminal `;` separates two real commands; must still be True
        assert compound_allow.is_multi_statement("a; b") is True

    def test_two_commands_both_semicolons_true(self):
        # `a; b;` — non-terminal `;` between a and b; must still be True
        assert compound_allow.is_multi_statement("a; b;") is True
