"""Compound Bash command detection for git-safety-guard's deny posture.

This module ONLY detects command shapes — it performs NO allow/safety
classification. There are two detection functions:

* ``is_multi_statement(command)`` — returns True if the command contains
  multi-statement shell constructs (pipes, ``;``, ``&&``, ``||``,
  substitutions, subshells, etc.). The hook blocks commands that return True
  here unless they are a blessed value-capture.

* ``is_blessed_value_capture(command)`` — returns True if the command is
  exactly a ``VAR=$(single-command)`` shape with no trailing content and no
  nested substitution inside the inner command. A blessed value-capture is NOT
  auto-allowed; it falls through to the normal CC permission prompt instead of
  being blocked. Any other multi-statement command is blocked.

Design contract
---------------
* NO settings/allowlist reading. No ``get_bash_rules``, no ``atom_is_allowed``,
  no ``decompose_atoms``.
* NO auto-allow surface. A value-capture that used to auto-allow when the inner
  command was allowlisted now falls through to the CC permission prompt. The
  prompt is the human gate.
* Never raises. Every public function self-guards and degrades gracefully on
  exception: ``is_multi_statement`` returns True (fail toward deny, never a
  hole), ``is_blessed_value_capture`` returns False (safe default).
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Deny-side primitives — called by _deny_compound_unless_blessed in git-safety-guard.py
# ---------------------------------------------------------------------------

# Compiled once: strip a trailing comment (preceded by whitespace or SOL) and
# everything after it. We apply this AFTER stripping quoted strings.
_TRAILING_COMMENT = re.compile(r"(?:(?<=\s)|^)#.*$")

# Signals that indicate a multi-statement command even after quote-stripping.
# NOTE: bare `&` is intentionally omitted — it also appears in fd-duplication
# redirects (2>&1, >&2, &>file, 2>&-, <&3). A separate regex check below
# distinguishes a real background `&` from a redirect `&`.
_MULTI_SIGNALS = (
    "\n",   # literal newline
    ";",    # statement separator
    "&&",   # and-list
    "||",   # or-list
    "|",    # pipeline
    "$(",   # command substitution
    "`",    # backtick substitution
    "(",    # subshell / grouping open
    ")",    # subshell / grouping close
    "{",    # brace group open
    "}",    # brace group close
    "<<",   # heredoc
)

# Matches a lone background-job `&` that is NOT part of a redirect context.
# Excluded by negative lookbehind: <, >, &, digit (covers 2>&1, >&2, 2>&-, <&3).
# Excluded by negative lookahead: &, > (covers &&, &>file).
_BACKGROUND_AMP = re.compile(r"(?<![<>&\d])&(?![&>])")

# Regex to strip quoted spans. Single-quoted strings are literal (no escapes);
# double-quoted strings allow \" escapes inside them. We replace matches with a
# single space to preserve token boundaries.
_QUOTED_SPAN = re.compile(r"'[^']*'|\"(?:[^\"\\]|\\.)*\"")

# Pattern for a blessed value-capture: `VAR=$(inner)` with nothing trailing.
_BLESSED_CAPTURE = re.compile(r"^\s*[A-Za-z_]\w*=\$\((.*)\)\s*$", re.DOTALL)


def is_multi_statement(command: str) -> bool:
    """Return True iff ``command`` contains multi-statement shell constructs.

    Preprocesses the command by:
      1. Stripping quoted strings (``'...'`` and ``"..."``) so metacharacters
         inside quotes are not counted.
      2. Stripping a trailing ``#``-comment (preceded by whitespace or SOL).

    Then returns True if the preprocessed string contains ANY of: a literal
    newline; ``;``, ``&&``, ``||``, or ``|``; ``$(`` or a backtick; ``(``,
    ``)``, ``{``, or ``}``; a trailing ``&``; or ``<<`` (heredoc).

    Redirects (``>`` / ``<``) are NOT triggers.

    No loop/control-keyword heuristic — ``for``/``while``/``if`` as bare words
    are NOT scanned; a shell loop necessarily contains ``;`` or a newline before
    ``do``/``done``, which the structural signals already catch.

    Self-guards: on any exception returns True (fail toward deny — a false-deny
    only costs the caller a single-command retry, never a security hole).

    Never raises.
    """
    try:
        # Step 1: strip quoted spans (replace with a space to keep boundaries)
        preprocessed = _QUOTED_SPAN.sub(" ", command)
        # Step 2: strip trailing comment
        preprocessed = _TRAILING_COMMENT.sub("", preprocessed)
        # Step 3: strip a single trailing `;` (with surrounding whitespace).
        # A lone trailing `;` is syntactically harmless — `echo hi;` is a
        # functionally single command.  Stripping it here prevents a false-deny
        # on `cmd;` and `cmd; # comment` patterns.  A non-terminal `;` (as in
        # `a; b`) is NOT trailing and survives into the signal scan below.
        preprocessed = preprocessed.rstrip()
        if preprocessed.endswith(";"):
            preprocessed = preprocessed[:-1].rstrip()
        # Scan for any substring multi-statement signal
        for signal in _MULTI_SIGNALS:
            if signal in preprocessed:
                return True
        # Step 4: detect a real background `&` via regex.  The bare `&` substring
        # check was removed from _MULTI_SIGNALS because it also matches inside
        # fd-duplication redirects (2>&1, >&2, &>file, 2>&-, <&3).  The regex
        # excludes those contexts while still catching `cmd &` and `a & b`.
        if _BACKGROUND_AMP.search(preprocessed):
            return True
        return False
    except Exception:
        return True  # fail toward deny


def is_blessed_value_capture(command: str) -> bool:
    """Return True iff ``command`` is exactly one value-capture assignment.

    A blessed value-capture has the form ``VAR=$(inner)`` where:
      * The WHOLE string (after stripping leading/trailing whitespace) matches
        ``VAR=$(...)`` with nothing trailing after the closing ``)``).
      * The captured ``inner`` is itself a SINGLE command: ``is_multi_statement(inner)``
        returns False.
      * The inner command contains no nested ``$(`` or backtick.

    A blessed value-capture is NOT auto-allowed. Instead, the hook lets it fall
    through to the normal CC permission prompt — the user (or CC's allowlist) decides.
    Any non-blessed multi-statement command is blocked by the hook.

    Returns False on any ambiguity or exception.

    Never raises.
    """
    try:
        m = _BLESSED_CAPTURE.match(command)
        if not m:
            return False
        inner = m.group(1)
        # Reject nested substitutions inside the inner command
        if "$(" in inner or "`" in inner:
            return False
        # Inner must be a single statement
        if is_multi_statement(inner):
            return False
        return True
    except Exception:
        return False
