"""Conservative auto-allow for compound Bash commands whose every atom is allowlisted.

Background
----------
Claude Code's permission allowlist matches a Bash command on its LEADING TOKEN.
A compound command — ``VAR=$(...)`` assignment, or any ``;`` / ``&&`` / ``||`` /
``|`` chain — has no single leading token matching an entry such as ``Bash(git *)``
or ``Bash(echo *)``. So a command whose every constituent is individually
allowlisted still falls through to a permission prompt every run.

This module folds a conservative auto-allow into the EXISTING ``git-safety-guard``
PreToolUse(Bash) hook (no new hook). It emits a PreToolUse ``allow`` decision ONLY
when the command is compound AND every decomposed atom matches an allow entry
derived AT RUNTIME from the user's settings files AND no atom matches a deny entry.

Safety contract (read before editing)
--------------------------------------
* This is a PRIVILEGE-ESCALATION surface: an ``allow`` decision BYPASSES the
  permission prompt. The bar is therefore "provably safe or fall through" — never
  "probably safe". Every ambiguity, parse failure, or construct we cannot fully
  decompose returns ``None`` (fall through to the normal prompt), NEVER an allow.
* The safe-set is DERIVED from the live ``settings.json`` + ``settings.local.json``
  allow list at call time — there is no hardcoded safe-list that could drift.
* The deny list is honored: any atom matching a deny entry returns ``None``.
* This module NEVER raises. Every public entry point self-guards and degrades to
  ``None`` on any exception, so it can never trip git-safety-guard's
  block-closed-on-exception top-level handler.
* ``should_auto_allow`` is the only intended caller surface. It returns ``True``
  only when ALL atoms are provably allowlisted; in every other case ``False``.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import shlex
from pathlib import Path

# ---------------------------------------------------------------------------
# Settings discovery
# ---------------------------------------------------------------------------

# Resolved once per process. Allowlist/denylist parsing reads small JSON files;
# caching avoids re-reading them on every Bash call within a session.
_SETTINGS_FILES = ("settings.json", "settings.local.json")

_cache: dict[str, tuple[frozenset[str], frozenset[str]]] = {}


def _claude_dir() -> Path:
    """Return the ~/.claude directory that holds the settings files."""
    return Path(os.path.expanduser("~")) / ".claude"


def _load_bash_rules(claude_dir: Path) -> tuple[frozenset[str], frozenset[str]]:
    """Return (allow_globs, deny_globs) of Bash(...) permission entries.

    Reads settings.json and settings.local.json, extracts ``permissions.allow``
    and ``permissions.deny`` entries of the form ``Bash(<pattern>)``, and returns
    the inner ``<pattern>`` strings. Non-Bash entries are ignored. Any read/parse
    error on a file is skipped (that file contributes nothing) — never raises.
    """
    allow: set[str] = set()
    deny: set[str] = set()
    bash_entry = re.compile(r"^Bash\((.*)\)$", re.DOTALL)
    for name in _SETTINGS_FILES:
        path = claude_dir / name
        try:
            data = json.loads(path.read_text())
        except (FileNotFoundError, OSError, ValueError):
            continue
        perms = data.get("permissions") if isinstance(data, dict) else None
        if not isinstance(perms, dict):
            continue
        for bucket, target in (("allow", allow), ("deny", deny)):
            entries = perms.get(bucket, [])
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, str):
                    continue
                m = bash_entry.match(entry.strip())
                if m:
                    target.add(m.group(1).strip())
    return frozenset(allow), frozenset(deny)


def get_bash_rules(claude_dir: Path | None = None) -> tuple[frozenset[str], frozenset[str]]:
    """Cached accessor for (allow_globs, deny_globs). Never raises."""
    try:
        base = claude_dir if claude_dir is not None else _claude_dir()
        key = str(base)
        if key not in _cache:
            _cache[key] = _load_bash_rules(base)
        return _cache[key]
    except Exception:
        return frozenset(), frozenset()


# ---------------------------------------------------------------------------
# Atom matching against allow/deny globs
# ---------------------------------------------------------------------------

def _matches_glob(atom: str, pattern: str) -> bool:
    """Match a normalized atom string against a single Bash(...) glob pattern.

    Claude Code's ``Bash(cmd *)`` semantics are prefix/glob: ``git *`` matches any
    command beginning ``git ``; ``pwd`` matches exactly ``pwd``. We mirror that with
    ``fnmatch`` (``*`` is the wildcard) plus the common exact-prefix case where a
    pattern ending in `` *`` should also match the bare command (e.g. ``git *``
    matches ``git`` with no args). We do NOT attempt to replicate every nuance —
    when in doubt the caller falls through, so a too-strict match is safe.
    """
    if atom == pattern:
        return True
    if fnmatch.fnmatchcase(atom, pattern):
        return True
    # `cmd *` should also cover the bare `cmd` (no trailing args).
    if pattern.endswith(" *") and atom == pattern[:-2]:
        return True
    return False


def atom_is_allowed(atom: str, allow: frozenset[str], deny: frozenset[str]) -> bool:
    """Return True iff ``atom`` matches an allow glob and NO deny glob.

    Deny takes precedence: an atom matching any deny entry is never allowed.
    """
    atom = atom.strip()
    if not atom:
        return False
    for pattern in deny:
        if _matches_glob(atom, pattern):
            return False
    return any(_matches_glob(atom, pattern) for pattern in allow)


# ---------------------------------------------------------------------------
# Compound detection + atom decomposition
# ---------------------------------------------------------------------------

# A command is "compound" (and thus a candidate for this path) if it contains a
# shell connector, a pipe, or a VAR=...$(...) assignment/substitution. A plain
# single command is NOT compound — CC's normal allowlist already handles it, so
# we never emit an allow for it (let the existing path do its job).
_COMPOUND_SIGNALS = re.compile(r"(;|&&|\|\||\|)|(\$\()|(`)|(^\s*[A-Za-z_][A-Za-z0-9_]*=)")

# Fragments that are NEVER part of a supported construct. Scanned up front,
# BEFORE substitution flattening. Their presence forces fall-through (return
# None) — we never emit allow for a command containing any of these.
#
# NOTE: `(`, `)`, and `&` are deliberately NOT here. They appear inside the
# supported `$(...)` substitution and the `&&`/`||` connectors, so an up-front
# scan for them would refuse every substitution and and/or-chain — the two most
# common compound forms — before they can be handled. They are caught PER-ATOM
# below (``_UNSAFE_IN_ATOM``), after substitutions are unwrapped and connectors
# are split out, where a genuine subshell `(...)` or background `&` still
# survives into an atom.
_UNSAFE_UPFRONT = (
    ">", "<",        # any redirect (covers >, >>, <, <<, &>, 2>, <(, >( fragments)
    "$((",           # arithmetic expansion
    "${",            # parameter expansion with operators — do not reason about it
    "{", "}",        # brace grouping / expansion
    "\n",            # multi-line command — out of scope
    "\\",            # line continuations / escapes — out of scope
)

# Shell metacharacters that must not survive into a final atom. After
# substitutions are unwrapped and connectors (`;`/`&&`/`||`/`|`) are split out,
# a legitimate atom is a flat ``cmd args`` string containing none of these. Any
# that remain signal a subshell, brace group, background job, exposed redirect,
# or an un-flattened/nested substitution — all of which force a refusal.
_UNSAFE_IN_ATOM = ("(", ")", "{", "}", "&", ">", "<", "$(", "`")

_UNSAFE_BUILTINS = {
    "eval", "exec", "source", ".", "trap", "command", "builtin", "env",
    "xargs", "find",  # can invoke arbitrary subcommands via -exec / args
    "sudo", "doas",
}


def is_compound(command: str) -> bool:
    """Return True iff the command looks compound (connector/pipe/assignment/subst)."""
    try:
        return bool(_COMPOUND_SIGNALS.search(command))
    except Exception:
        return False


def _strip_one_substitution_layer(text: str) -> str | None:
    """Unwrap a single ``$(...)`` or backtick substitution layer in ``text``.

    Replaces each top-level ``$(...)`` / `` `...` `` occurrence with the INNER
    command text joined into the surrounding text by a connector, so the result
    can be re-split into atoms. Returns the rewritten string, or None if the text
    contains a NESTED substitution (depth > 1) or unbalanced delimiters — both of
    which we refuse to reason about (fall through).

    Example: ``REPO=$(git rev-parse --show-toplevel)`` -> ``REPO= ; git rev-parse
    --show-toplevel`` (the empty-LHS assignment atom is dropped later).
    """
    # Backticks: only the simple, non-nested case. Any backtick at all that we
    # cannot pair cleanly → refuse.
    if "`" in text:
        if text.count("`") % 2 != 0:
            return None
        # Replace paired backticks with `;` delimiters around their content.
        parts = text.split("`")
        # parts alternate outside/inside; inside segments are at odd indices.
        rebuilt = []
        for i, seg in enumerate(parts):
            if i % 2 == 1:  # inside a backtick pair
                if "`" in seg or "$(" in seg:
                    return None  # nested → refuse
                rebuilt.append(" ; " + seg + " ; ")
            else:
                rebuilt.append(seg)
        text = "".join(rebuilt)

    # $() substitutions: walk and replace top-level ones; refuse on nesting.
    out = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "$" and i + 1 < n and text[i + 1] == "(":
            depth = 1
            j = i + 2
            start = j
            while j < n and depth > 0:
                if text[j] == "(" :
                    depth += 1
                elif text[j] == ")":
                    depth -= 1
                elif text[j] == "$" and j + 1 < n and text[j + 1] == "(":
                    return None  # nested $( ... $( ... ) ... ) → refuse
                j += 1
            if depth != 0:
                return None  # unbalanced → refuse
            inner = text[start:j - 1]
            if "$(" in inner or "`" in inner:
                return None  # nested → refuse
            out.append(" ; " + inner + " ; ")
            i = j
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


# Connector splitter: split on ; && || | (after substitutions are flattened).
_CONNECTOR = re.compile(r"\s*(?:&&|\|\||;|\|)\s*")

# An assignment-prefix atom like ``REPO=`` or ``FOO=bar`` (leading on a command).
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def decompose_atoms(command: str) -> list[str] | None:
    """Decompose a compound command into normalized command atoms, or None.

    Returns a list of atom strings (each the COMMAND portion after any leading
    ``VAR=`` prefix is stripped), or None if the command contains any construct we
    refuse to reason about (redirects, nesting, grouping, escapes, etc.).

    The returned atoms are exactly what must each match the allowlist. An atom that
    is a pure assignment with no command (``REPO=``) is dropped — it executes
    nothing and needs no permission.

    Never raises.
    """
    try:
        # Reject unambiguously-unsafe fragments up front. `(`/`)`/`&` are NOT in
        # this set (see _UNSAFE_UPFRONT) — they belong to the supported `$(...)`
        # substitution and `&&`/`||` connectors and are caught per-atom below.
        for frag in _UNSAFE_UPFRONT:
            if frag in command:
                return None

        flattened = _strip_one_substitution_layer(command)
        if flattened is None:
            return None

        # Flattening can expose a redirect that lived inside a substitution
        # (e.g. `echo $(cat x > y)`); re-scan the up-front set on the result.
        for frag in _UNSAFE_UPFRONT:
            if frag in flattened:
                return None

        raw_atoms = _CONNECTOR.split(flattened)
        atoms: list[str] = []
        for raw in raw_atoms:
            seg = raw.strip()
            if not seg:
                continue
            # No shell metacharacter may survive into a final atom. After
            # substitutions are unwrapped and connectors are split out, a genuine
            # subshell `(...)`, brace group, background `&`, exposed redirect, or
            # un-flattened/nested substitution leaves one of these behind — refuse
            # rather than reason about it.
            if any(frag in seg for frag in _UNSAFE_IN_ATOM):
                return None
            # Strip a leading VAR= assignment prefix (and any chain of them, e.g.
            # `A=1 B=2 cmd`). Tokenize to find the first non-assignment token.
            try:
                tokens = shlex.split(seg)
            except ValueError:
                return None  # unbalanced quoting → refuse
            if not tokens:
                continue
            # Drop leading VAR=value env-prefix tokens.
            idx = 0
            while idx < len(tokens) and _ASSIGNMENT.match(tokens[idx]) and "=" in tokens[idx]:
                idx += 1
            if idx >= len(tokens):
                # Pure assignment atom (no command) — executes nothing, drop it.
                continue
            cmd_tokens = tokens[idx:]
            # Reconstruct a normalized atom string from the command tokens. We use
            # the original leading token + its args joined by single spaces. This
            # is what we match against `Bash(cmd *)` globs.
            atom = " ".join(cmd_tokens)
            atoms.append(atom)
        return atoms
    except Exception:
        return None


def _atom_head_is_safe(atom: str) -> bool:
    """Return False if the atom's leading token is an unsafe metaprogramming builtin."""
    try:
        head = atom.split(None, 1)[0]
    except (IndexError, ValueError):
        return False
    # Strip any path prefix: /usr/bin/env -> env.
    head = head.rsplit("/", 1)[-1]
    return head not in _UNSAFE_BUILTINS


def should_auto_allow(command: str, claude_dir: Path | None = None) -> bool:
    """Return True iff this compound command's every atom is provably allowlisted.

    The full gate:
      1. The command must be compound (otherwise CC's normal allowlist applies —
         we do not interfere).
      2. It must decompose cleanly into atoms (no refused construct).
      3. Every atom's head must not be an unsafe metaprogramming builtin.
      4. Every atom must match an allow glob and no deny glob, derived at runtime
         from the live settings files.

    Any failure → False (caller falls through to the normal permission prompt).
    Never raises.
    """
    try:
        if not is_compound(command):
            return False
        atoms = decompose_atoms(command)
        if not atoms:
            return False  # None (refused) or empty (nothing to allow)
        allow, deny = get_bash_rules(claude_dir)
        if not allow:
            return False  # no allowlist to derive safety from → fall through
        for atom in atoms:
            if not _atom_head_is_safe(atom):
                return False
            if not atom_is_allowed(atom, allow, deny):
                return False
        return True
    except Exception:
        return False
