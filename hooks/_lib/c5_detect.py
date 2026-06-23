# skills/coding-team/hooks/_lib/c5_detect.py
"""C5 (test-hermeticity) pure detector — shared by the all-advisory C5 adapter
in ``graduated_checks.py`` (PreToolUse Edit|Write), covering both Python (``.py``,
test-file-path gated) and Rust (``.rs``).  This is an author-time ADVISORY, never
a commit block.

PURE: no I/O, no subprocess, no filesystem. Given test-file text + a language,
returns a finding describing a POSITIVELY-recognized ungated open against an
external/shared/non-ephemeral resource, or None.

CONSERVATIVE-GATE RULE (operator condition 2): on ANY unrecognized, ambiguous,
or conditional attribute/macro present on the test, treat the test as GATED and
return None. Fail toward NOT-detecting, never toward detecting on uncertainty.
(This trims false-positive advisory noise; it was originally a zero-FP hard
requirement for the blocking pilot, and is now belt-and-suspenders precision.)

Gate scan strips WHOLE-LINE comments (`//` Rust, `#` Python) before the
gate/ephemeral test — this kills the comment-spoof FN the spike actually measured
(a gate token on its own comment line).

Rust inline `//` comment tails are also stripped by the shared `_rust_code_only`
normalizer (string-literal contents are stripped FIRST, making the subsequent
`//`-strip safe even for lines containing `https://` URLs inside string literals).
This eliminates the Codex F4 inline-comment FN: a real open followed by a trailing
`// tempfile` now correctly fires instead of being suppressed (recall improvement,
never a false-positive). The Python path still uses whole-line-only `#` stripping
(Python inline `#` in a URL or path literal is more ambiguous; the advisory path
is fail-open so the residual FN there remains acceptable).

May raise on a malformed input; callers (the advisory adapter) wrap in
try/except->None. See c05-test-hermeticity.md and SPIKE-RESULTS.md.
"""
import re
from dataclasses import dataclass
from typing import Literal


@dataclass
class C5Finding:
    """A positively-recognized ungated external-resource open in a test."""
    signature: str          # the matched open, e.g. "AxonService::open("
    lang: Literal["rust", "python"]


# --- Rust ---------------------------------------------------------------
# RUST_OPEN: positively-recognized external-resource opens.
_RUST_OPEN = re.compile(
    r"(?:Database|AxonService)::open\s*\("
    r"|download_model_files\s*\("
    r"|CandleEmbedder::new\s*\("
)
# Gate tokens scanned on REAL #[...] attribute lines only.
_RUST_GATE_IGNORE = re.compile(r"#\[\s*ignore")
_RUST_GATE_CFG_FEATURE = re.compile(r"#\[\s*cfg\s*\(\s*feature")
# cfg_attr(..., ignore) — both substrings present on the attribute text.
# The test-attribute itself (harmless — not a gate).
_RUST_TEST_ATTR = re.compile(r"#\[\s*(?:test|tokio::test|rstest)\b")
# Ephemeral construction markers.
# `tempfile` (bare) covers `tempfile::tempdir(...)`.  Previously a trailing
# `// tempfile` comment also suppressed detection (Codex F4 accepted FN) because
# inline comments were not stripped.  The shared _rust_code_only normalizer (FIX 5)
# strips `//` tails AFTER stripping string contents, so inline-comment spoofing is
# no longer possible on the Rust advisory path; the F4 FN is eliminated.
_RUST_EPHEMERAL = re.compile(
    r"open_memory|tempfile|TempDir::new|tmp\.path\(\)"
    r"|new_for_test|new_in_memory"
)


def _strip_line_comments(text: str, prefix: str) -> str:
    """Drop whole-line comments so a commented-out gate is not read as a gate."""
    return "\n".join(
        line for line in text.splitlines()
        if not line.lstrip().startswith(prefix)
    )


def _rust_gated(attr_text: str) -> bool:
    """True iff a recognized gate is present, OR an unrecognized/ambiguous/
    conditional attribute is present (CONSERVATIVE-GATE: unknown -> treat gated).

    ``attr_text`` is the attribute block of ONE test function ONLY (its contiguous
    #[...] lines, including multiline continuations) — NEVER the whole file.
    Scanning the whole file would treat a #[derive(...)]/#[allow(...)] on any
    unrelated struct as an 'unrecognized attribute' and suppress every finding in
    that file (near-total recall loss). The operator rule is 'unknown gate form ON
    THE TEST', so the unit must be scoped to the test's own attributes.

    FIX 1: the recognized-gate checks now use plain substring / DOTALL-capable
    patterns so they match across multiline attribute text.  The conservative-gate
    check iterates over ``#[``-introduced spans in the text using a bracket-depth
    scan so that multiline attrs are each treated as ONE attribute, and only the
    test attribute itself (``#[test]``, ``#[tokio::test]``, ``#[rstest]``) is
    exempted.  Any other ``#[``-introduced attribute → conservative gated.
    """
    # Recognized-gate checks — substring-safe across multiline text.
    if _RUST_GATE_IGNORE.search(attr_text):
        return True
    if "cfg_attr" in attr_text and "ignore" in attr_text:
        return True
    if _RUST_GATE_CFG_FEATURE.search(attr_text):
        return True

    # CONSERVATIVE-GATE: iterate over each #[...]-introduced attribute span
    # in the attr_text.  A single-line ``#[foo]`` is matched by the simple
    # ``#\[[^\]]*\]`` pattern, but a multiline ``#[cfg_attr(\n...\n)]`` is not
    # (``[^\]]`` stops at the first ``]`` in the content).  We therefore scan
    # by bracket depth: each ``#[`` starts a new attribute; we consume until
    # the enclosing ``]`` is balanced.
    pos = 0
    text_len = len(attr_text)
    while pos < text_len:
        hash_bracket = attr_text.find("#[", pos)
        if hash_bracket == -1:
            break
        # Collect the full attribute span by tracking bracket depth.
        depth = 0
        span_start = hash_bracket
        k = hash_bracket
        while k < text_len:
            ch = attr_text[k]
            if ch == "[" or ch == "(":
                depth += 1
            elif ch == "]" or ch == ")":
                depth -= 1
                if depth <= 0:
                    k += 1
                    break
            k += 1
        span = attr_text[span_start:k]
        pos = k

        # The harmless test attribute itself does not count as an unknown gate.
        if _RUST_TEST_ATTR.search(span):
            continue
        # Any other #[...] attribute on THIS TEST → conservative gated.
        return True

    return False


def _is_attr_region_line(line: str) -> bool:
    """True iff this line belongs to a Rust attribute region.

    Recognised: lines starting with ``#[``, ``//`` comments, ``/*`` block-comment
    openers/closers/continuations, blank lines, and attribute-continuation lines
    that are part of a multiline ``#[...\n...\n]`` attribute (parentheses and
    square-bracket continuation lines such as ``    not(feature = "x"),``,
    ``    ignore``, and ``)]``).  Continuation lines of open brackets are handled
    by the caller which tracks bracket depth.
    """
    stripped = line.lstrip()
    if not stripped:
        return True
    if stripped.startswith("#["):
        return True
    if stripped.startswith("//"):
        return True
    if stripped.startswith("/*") or stripped.startswith("*") or stripped.startswith("*/"):
        return True
    return False


# ---------------------------------------------------------------------------
# String / char-literal strip patterns (used by both the upward-walk per-line
# helper and the forward-reading full-text normalizer below).
# Defined here, before their first use in _strip_comment_text_for_bracket_count.
# ---------------------------------------------------------------------------
_RUST_RAW_STR = re.compile(
    r'r(#+)".*?"\1',
    re.DOTALL,
)
_RUST_NORMAL_STR = re.compile(
    r'"(?:\\.|[^"\\])*"',
    re.DOTALL,
)
_RUST_CHAR_LITERAL = re.compile(
    r"'(?:\\.|[^'\\])'"
)

# Patterns used to strip comment text from a line before bracket-depth counting.
# These remove comment content so that brackets inside comments (e.g. `/* ) */`)
# do not fabricate phantom close_debt and overrun the upward attr-region walk.
_RUST_INLINE_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_RUST_LINE_COMMENT_TAIL = re.compile(r"//.*$", re.MULTILINE)


def _strip_comment_text_for_bracket_count(line: str, in_block_comment: bool) -> tuple[str, bool]:
    """Return (code_text_only, still_in_block_comment) for one source line.

    Strips BOTH comment content AND string/char-literal content so that
    delimiters inside either are not counted toward close_debt.  This is
    site 2 of the shared normalizer class — the per-line upward-walk variant
    that also threads block-comment state across iterations.

    Handles three comment cases (going UPWARD through lines, so ``*/`` appears
    before ``/*`` in iteration order):
    1. The line is inside an already-open block comment (upward sense:
       ``*/`` was seen on a lower line) — suppress everything until ``/*``.
    2. Complete ``/* ... */`` inline spans on this line — remove them.
    3. ``//`` line-comment tails — strip from ``//`` onward.
    After comment stripping, string/char-literal contents are also removed via
    ``_rust_code_only`` (which strips raw strings, normal strings, char literals).

    Returns the cleaned code text and the updated ``in_block_comment`` state.
    """
    text = line
    # If we are inside a block comment (upward sense: already saw `*/` below),
    # suppress all of it until `/*` closes the comment going upward.
    if in_block_comment:
        if "/*" in text:
            idx = text.index("/*")
            text = text[:idx]
            in_block_comment = False
        else:
            return ("", True)
    # Strip complete /* ... */ inline spans.
    text = _RUST_INLINE_BLOCK_COMMENT.sub("", text)
    # If `*/` remains (not removed by inline stripping), it opens a new upward
    # block-comment context.
    if "*/" in text:
        idx = text.index("*/")
        text = text[:idx]
        in_block_comment = True
    # Strip `//` line-comment tails.
    text = _RUST_LINE_COMMENT_TAIL.sub("", text)
    # Strip string/char-literal contents so e.g. `"]"` or `"{"` in an attribute
    # string do not corrupt bracket counts (site 2 of the normalizer class).
    text = _RUST_RAW_STR.sub(lambda m: f'r{m.group(1)}""{m.group(1)}', text)
    text = _RUST_NORMAL_STR.sub('""', text)
    text = _RUST_CHAR_LITERAL.sub("''", text)
    return (text, in_block_comment)


def _rust_test_units(text: str):
    """Yield (attr_block, body) per #[test]-anchored fn. attr_block = the contiguous
    attribute/comment/blank lines directly above the fn; body = the fn signature line
    through its brace-matched end. Per-function scoping is what makes the
    conservative-gate correct (a struct's #[derive] is in NO test unit's attr_block).

    FIX 1: the upward walk now handles multiline attributes and block comments.
    Rustfmt may wrap a long ``#[cfg_attr(..., ignore)]`` across several lines;
    the continuation lines (``    not(...),``, ``    ignore``, ``)]``) do not start
    with ``#[``, so the original walk stopped prematurely and lost the gate.

    FIX 4: the close_debt bracket counter now strips comment text (``//`` tails,
    ``/* ... */`` inline spans, and multiline block comments) before counting
    brackets.  A ``/* ) */`` line above ``#[test]`` previously injected phantom
    close_debt, overrunning the attr-region walk into surrounding module attrs
    (``#[cfg(test)]``) which _rust_gated treated as an unknown gate and suppressed
    a real violation.  After this fix, only REAL attribute-syntax brackets count.

    FIX A: the body brace-depth walk now uses the stateful cross-line normalizer
    ``_rust_code_only_line`` which threads ``in_block_comment``, ``in_raw_string``
    (with hash count), and ``in_normal_string`` across lines.  Previously the
    per-line ``_rust_code_only`` regex applied DOTALL patterns to each line in
    isolation, so a multi-line raw string ``r#"\\n{\\n"#`` had its interior ``{``
    line pass through unstripped, inflating depth and absorbing the next test unit.

    FIX B: conservative structural cap.  Even if the stateful normalizer has a
    gap, the body walk hard-stops when it encounters a line that starts the NEXT
    test unit's attribute region (a ``#[test]``/``#[ignore]``/``#[tokio::test]``/
    ``#[rstest]`` attr line, or a ``fn `` at the same-or-lower indentation as the
    current test fn), before the brace closes.  If depth is still > 0 at that
    boundary, we miscounted — the safe resolution is to end the current unit
    (at worst a fail-open-safe FN), never to merge two units (which would
    misattribute a gated open to an ungated unit = a false advisory nudge).

    We use a "pending close debt" tracker going upward through source lines:
    - Going upward, a line with MORE `]`/`)` than `[`/`(` in its CODE (non-comment)
      text signals that there must be an unmatched open bracket ABOVE — we MUST
      keep walking upward to capture the full attribute.
    - ``close_debt`` accumulates unmatched closing brackets encountered so far;
      when it is > 0 we are "inside" a multiline attribute that spans above us.
    - Block-comment lines (``/* ... */``) between attrs are accepted as attr-region
      lines (they don't break the walk) but contribute ZERO bracket debt.
    """
    lines = text.splitlines()
    n = len(lines)
    i = 0
    while i < n:
        if re.search(r"\bfn\s+\w+", lines[i]):
            fn_indent = len(lines[i]) - len(lines[i].lstrip())
            j, attrs, saw_test = i - 1, [], False
            # close_debt > 0 means the lines collected so far (below in source
            # order) have more `]`/`)` than `[`/`(` in code (non-comment) text,
            # so there must be an unmatched `#[`/`(` somewhere above.
            close_debt = 0
            # FIX 4: track multiline block-comment state as we walk upward.
            # Going upward, `*/` opens suppression and `/*` closes it.
            in_block_comment = False
            while j >= 0:
                line = lines[j]
                stripped = line.lstrip()

                # FIX 4: capture block-comment state BEFORE processing this line
                # so condition (d) can use the pre-update value.
                was_in_block_comment = in_block_comment

                # Strip comment content from this line, updating in_block_comment
                # for the NEXT upward iteration.
                code_only, in_block_comment = _strip_comment_text_for_bracket_count(
                    line, in_block_comment
                )
                line_opens = code_only.count("[") + code_only.count("(")
                line_closes = code_only.count("]") + code_only.count(")")
                net_closes = line_closes - line_opens   # positive = more close brackets

                # Include this line if:
                # (a) it is recognisably part of an attribute region (incl. block
                #     comment lines, which are accepted but contribute zero debt), OR
                # (b) we still have unmatched closes from lines already collected
                #     (we are inside a multiline attribute), OR
                # (c) this line contributes unmatched closes in CODE (non-comment)
                #     text — it is the closing half of a multiline attribute, OR
                # (d) was_in_block_comment — this line is inside a block comment
                #     whose `*/` was seen on a lower line; include it so the
                #     comment body doesn't truncate collection before `/*` is found.
                is_attr_line = _is_attr_region_line(stripped)
                in_multiline = close_debt > 0
                starts_close = net_closes > 0

                if not (is_attr_line or in_multiline or starts_close or was_in_block_comment):
                    break

                attrs.append(line)
                if _RUST_TEST_ATTR.search(line):
                    saw_test = True
                # Update close_debt using ONLY code (non-comment) bracket counts
                # so comment brackets never fabricate phantom debt (FIX 4).
                close_debt += net_closes
                if close_debt < 0:
                    close_debt = 0
                j -= 1
            if saw_test:
                depth, started, body, k = 0, False, [], i
                # FIX A: stateful cross-line normalizer threads string/comment
                # context across lines so multi-line string/raw-string interiors
                # are correctly suppressed in brace counting.
                line_state = _RustLineState()
                while k < n:
                    raw_line = lines[k]

                    # FIX B: conservative structural cap — stop the body at the
                    # start of the NEXT test unit's attribute region, even if
                    # depth still looks > 0 (which would indicate a miscount).
                    # A worst-case miscount produces a fail-open-safe FN; it never
                    # merges two units and misattributes a gated open to an ungated
                    # unit (which would be a false advisory nudge).
                    # Trigger conditions (only after the body has started so we
                    # don't immediately stop at the fn line itself):
                    #   (i)  a line matching a test attribute (#[test], #[ignore],
                    #        #[tokio::test], #[rstest]) at or before fn_indent
                    #   (ii) a `fn ` line at indentation <= fn_indent (i.e., a
                    #        sibling or parent fn, not a nested closure).
                    if started and k > i:
                        raw_stripped = raw_line.lstrip()
                        raw_indent = len(raw_line) - len(raw_stripped)
                        if _RUST_NEXT_UNIT_ATTR.match(raw_line) and raw_indent <= fn_indent:
                            # Step back: the body ends BEFORE this attr line.
                            k -= 1
                            break
                        if re.search(r"\bfn\s+\w+", raw_line) and raw_indent <= fn_indent:
                            k -= 1
                            break

                    # FIX A (site 1): use stateful normalizer; brace COUNTING
                    # on code-only text, line CLASSIFICATION on original.
                    co = _rust_code_only_line(raw_line, line_state)
                    depth += co.count("{") - co.count("}")
                    body.append(raw_line)
                    if "{" in co:
                        started = True
                    if started and depth <= 0:
                        break
                    k += 1
                yield ("\n".join(reversed(attrs)), "\n".join(body))
                i = k + 1
                continue
        i += 1


# ---------------------------------------------------------------------------
# Shared Rust code-only normalizer — closes the "raw delimiter counting" class
# ---------------------------------------------------------------------------
# All four sites that COUNT delimiters or SEARCH for signatures in Rust source
# must operate on code-only text (no string/char-literal or comment content).
# A single helper composes both strip passes so no site is missed.
#
# Ordering:
#   1. Raw strings FIRST (r#"..."#) so the r# prefix is consumed whole and
#      cannot be mistaken for an identifier.
#   2. Normal double-quoted strings.
#   3. Char literals.
#   4. Inline /* ... */ block-comment spans.
#   5. // line-comment tails.
#
# Steps 4-5 are applied to the FULL multi-line text here (forward-reading,
# for the body / attr scan sites).  The upward attr-walk's per-line comment
# stripping uses _strip_comment_text_for_bracket_count (which tracks block-
# comment state across upward iterations) AND additionally strips string
# contents via this helper — see _strip_comment_text_for_bracket_count.
#
# The replacement for string contents is empty delimiters ("" / '' / r#""#)
# so delimiters never shift line numbers and the string's structural position
# is preserved.  Placeholder content `` never matches _RUST_OPEN.

# Forward-reading inline block-comment and line-comment patterns used by the
# full-text normalizer.  (_RUST_RAW_STR, _RUST_NORMAL_STR, _RUST_CHAR_LITERAL
# are defined earlier — before _strip_comment_text_for_bracket_count.)
_RUST_FWD_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_RUST_FWD_LINE_COMMENT = re.compile(r"//[^\n]*", re.MULTILINE)

# Pattern for recognizing the start of a new test attribute on a line that
# belongs to the NEXT unit's attribute block (FIX B structural cap).
_RUST_NEXT_UNIT_ATTR = re.compile(
    r"^\s*#\[\s*(?:test|tokio::test|rstest|ignore)\b"
)


def _rust_code_only(text: str) -> str:
    """Return Rust source text with ALL string/char-literal and comment content
    replaced by empty placeholders.

    Used for multi-line batch normalization (attrs scan, ``_RUST_OPEN`` search,
    and ``_rust_gated`` bracket-span).  For the body brace-depth walk — which
    processes lines one at a time and must thread string state across lines —
    use ``_RustLineState`` + ``_rust_code_only_line`` instead.

    NOT a full Rust lexer — best-effort for the common cases.  Over-stripping
    is safe: a placeholder never matches _RUST_OPEN, and empty braces/brackets
    do not shift delimiter counts.

    IMPORTANT: line CLASSIFICATION (``_is_attr_region_line``, ``fn`` detection,
    ``_RUST_TEST_ATTR`` search) still operates on the ORIGINAL text — only the
    counting/searching uses this output.
    """
    # 1. Raw strings — must come before normal strings.
    text = _RUST_RAW_STR.sub(lambda m: f'r{m.group(1)}""{m.group(1)}', text)
    # 2. Normal double-quoted strings.
    text = _RUST_NORMAL_STR.sub('""', text)
    # 3. Char literals.
    text = _RUST_CHAR_LITERAL.sub("''", text)
    # 4. Inline /* ... */ block-comment spans (forward-reading, full text).
    text = _RUST_FWD_BLOCK_COMMENT.sub("", text)
    # 5. // line-comment tails.
    text = _RUST_FWD_LINE_COMMENT.sub("", text)
    return text


# ---------------------------------------------------------------------------
# FIX A — stateful cross-line normalizer for the downward body brace walk
# ---------------------------------------------------------------------------
# The per-line `_rust_code_only` regex approach does not thread string state
# across lines.  A multi-line raw string r#"\n{\n"# has its '{' on a separate
# line that, processed in isolation, looks like plain code — so the brace
# inflates depth and causes one unit to absorb the next (unit-merge).
#
# The stateful normalizer walks each character of a line and carries four
# pieces of cross-line state into the next line:
#
#   in_block_comment (bool)  — inside a /* ... */ block comment
#   in_raw_string (int)      — 0 = not in raw string; N>0 = currently inside
#                              an r#"..."# with N '#' hashes (the closing
#                              delimiter is '"' followed by exactly N '#' chars)
#   in_normal_string (bool)  — inside a "..." normal string (spans lines)
#   in_char_literal (bool)   — inside a '.' char literal (single-line only;
#                              carried for symmetry but closes within a line)
#
# Direction: DOWNWARD (forward).  `r#"` OPENS raw string, `"#` (matching
# hash count) CLOSES it.  `/*` OPENS block comment, `*/` CLOSES it.
# `"` OPENS/CLOSES normal string (with backslash-escape handling).
# `//` OPENS line comment (runs to end of line; always closes within the line).
#
# This is the INVERSE of the upward walk's semantics — do NOT reuse
# _strip_comment_text_for_bracket_count here.

class _RustLineState:
    """Mutable carrier for cross-line lexer state in the downward body walk."""
    __slots__ = ("in_block_comment", "in_raw_string", "raw_string_hashes",
                 "in_normal_string")

    def __init__(self) -> None:
        self.in_block_comment: bool = False
        self.in_raw_string: bool = False   # True when inside any raw string
        self.raw_string_hashes: int = 0    # number of '#' in the delimiter
        self.in_normal_string: bool = False

    def copy(self) -> "_RustLineState":
        s = _RustLineState()
        s.in_block_comment = self.in_block_comment
        s.in_raw_string = self.in_raw_string
        s.raw_string_hashes = self.raw_string_hashes
        s.in_normal_string = self.in_normal_string
        return s


def _rust_code_only_line(line: str, state: "_RustLineState") -> str:
    """Return the code-only portion of one Rust source line, updating ``state``
    in place to carry cross-line lexer context to the next line.

    Only characters that are NOT inside a string literal or comment contribute
    to the returned string.  Newlines are not emitted (the caller works line
    by line).

    State threading (downward / forward direction):
    - ``state.in_block_comment``: set when ``/*`` is seen outside a string,
      cleared when ``*/`` is seen.
    - ``state.in_raw_string`` + ``state.raw_string_hashes``: ``in_raw_string``
      is set to True when ``r`` followed by N ``#`` chars followed by ``"`` is
      seen outside other contexts; ``raw_string_hashes`` is set to N (may be 0
      for bare ``r"..."``); cleared when ``"`` followed by exactly N ``#`` chars
      is seen inside the raw string.
    - ``state.in_normal_string``: set when ``"`` is seen outside other contexts,
      cleared when an unescaped ``"`` closes it (backslash sequences inside the
      string are consumed as pairs so they don't accidentally close the string).

    Char literals are handled inline (they open and close within a line) — no
    cross-line state needed for them; they use the existing per-line char-literal
    regex on the code-only result, so they are not separately threaded here.

    ``//`` line comments are handled inline: when ``//`` is seen outside string/
    comment context, we stop processing the rest of the line (the comment runs
    to end-of-line and never crosses to the next line).
    """
    out: list[str] = []
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]

        # ── inside a block comment ────────────────────────────────────────────
        if state.in_block_comment:
            if ch == "*" and i + 1 < n and line[i + 1] == "/":
                state.in_block_comment = False
                i += 2
            else:
                i += 1
            continue

        # ── inside a raw string ───────────────────────────────────────────────
        if state.in_raw_string:
            hashes = state.raw_string_hashes
            if ch == '"':
                # Check for the closing delimiter: '"' followed by exactly
                # `hashes` '#' chars (0 for r"...", 1 for r#"..."#, etc.).
                end = i + 1
                count = 0
                while end < n and line[end] == "#" and count < hashes:
                    count += 1
                    end += 1
                if count == hashes:
                    state.in_raw_string = False
                    state.raw_string_hashes = 0
                    i = end
                else:
                    i += 1
            else:
                i += 1
            continue

        # ── inside a normal string ────────────────────────────────────────────
        if state.in_normal_string:
            if ch == "\\":
                i += 2   # consume escape sequence (backslash + escaped char)
            elif ch == '"':
                state.in_normal_string = False
                i += 1
            else:
                i += 1
            continue

        # ── outside all string/comment contexts ───────────────────────────────

        # Line comment: rest of line is a comment, stop.
        if ch == "/" and i + 1 < n and line[i + 1] == "/":
            break

        # Block comment opener.
        if ch == "/" and i + 1 < n and line[i + 1] == "*":
            state.in_block_comment = True
            i += 2
            continue

        # Raw string opener: r followed by zero-or-more '#' followed by '"'.
        if ch == "r":
            j = i + 1
            hash_count = 0
            while j < n and line[j] == "#":
                hash_count += 1
                j += 1
            if j < n and line[j] == '"':
                # Valid raw string opener.  hash_count may be 0 (for r"...").
                state.in_raw_string = True
                state.raw_string_hashes = hash_count
                i = j + 1
                continue
            # Not a raw string opener — fall through and emit 'r'.

        # Normal string opener.
        if ch == '"':
            state.in_normal_string = True
            i += 1
            continue

        # Char literal: consumed in one shot here (single-line; no cross-line
        # state needed). A char literal is `'` + (escape or single char) + `'`.
        # We match conservatively: only consume if the pattern closes within
        # this line (i.e. we see closing `'`).  If not, emit the `'` as code.
        if ch == "'":
            # Try to match: '\x' (2-char escape) or '.' (single char) followed
            # by closing `'`.  This is good-enough for real Rust char literals.
            if i + 2 < n and line[i + 1] == "\\" and i + 3 < n and line[i + 3] == "'":
                # Escape sequence: '\x' or '\n' etc.
                out.append("''")
                i += 4
                continue
            elif i + 2 < n and line[i + 2] == "'":
                out.append("''")
                i += 3
                continue
            # Not a closed char literal — emit raw.

        # Regular code character — emit it.
        out.append(ch)
        i += 1

    return "".join(out)


def _detect_rust(text: str) -> "C5Finding | None":
    # Per-test-function: scan THIS fn's attrs for gates, THIS fn's body for the open.
    for attrs, body in _rust_test_units(text):
        # Normalize once for each per-function unit; all counting/searching below
        # uses these code-only strings — never the raw attrs/body text.
        attrs_co = _rust_code_only(_strip_line_comments(attrs, "//"))
        body_co = _rust_code_only(_strip_line_comments(body, "//"))

        # Site 4: _RUST_OPEN signature search on code-only body.
        m = _RUST_OPEN.search(body_co)
        if not m:
            continue
        # Site 3: _rust_gated gate-span scan on code-only attrs.
        if _rust_gated(attrs_co):
            continue
        # Ephemeral check on code-only body.  Note: _RUST_EPHEMERAL includes
        # bare ``tempfile`` which previously matched inline-comment tails (Codex
        # F4 FN).  On the code-only path those tails are stripped, so the FN is
        # no longer present here — the test that documents it now sees FIRES.
        # That test asserted current (non-firing) behavior as a DOCUMENTED FN;
        # updating it to FIRES is correct — it means we fixed a false-negative.
        if _RUST_EPHEMERAL.search(body_co):
            continue
        return C5Finding(signature=m.group(0), lang="rust")
    return None


# --- Python -------------------------------------------------------------
# PY_PRECISE_OPEN: persistent/real external opens (the spike's A_precise list).
_PY_PRECISE_OPEN = re.compile(
    r"""sqlite3\.connect\(\s*["'](?!:memory:)(?!/tmp)(?!.*tmp_path)[^"']*["']\)"""
    r"""|requests\.(?:get|post)\(\s*["']https?://"""
    r"""|httpx\.(?:Client|AsyncClient)\([^)]*\)\.(?:get|post)\(\s*["']https?://"""
    r"""|SentenceTransformer\("""
    r"""|AutoModel"""
    r"""|socket\.create_connection\(\s*\("""
)
_PY_GATE = re.compile(
    r"@pytest\.mark\.(?:skipif|benchmark|integration|slow)"
    r"|pytest\.importorskip"
    r"|pytest\.skip\("
    r"|os\.environ\.get\([^)]*\).*skip"        # env-skip
)
_PY_EPHEMERAL = re.compile(
    # Ephemeral path fixtures — word-bounded so they don't match mid-identifier.
    r"\btmp_path\b|\btmpdir\b|\btempfile\b|\bTemporaryDirectory\b|\bNamedTemporaryFile\b"
    # In-memory DB sentinel (literal string fragment, not a word token).
    r"|:memory:"
    # ASGI in-process transport (suppresses httpx/requests wired to app=app).
    r"|app="
    # FIX 3: tighten mock/patch tokens so that URL path segments like /mock/ or
    # /patch/ inside string literals do not suppress the advisory.
    # `mock` and `patch` inside a URL appear as /mock/ or /patch/ — the token is
    # preceded by '/'.  We use a negative lookbehind (?<![/\w]) to exclude that
    # case: the token must NOT be immediately preceded by '/' or a word char
    # (which would indicate it is part of a URL path or a larger identifier).
    # @patch / patch( / mock.something / standalone mock still match because '@',
    # whitespace, and '.' are neither '/' nor word characters.
    # Named subclasses (AsyncMock) use a plain \b form since they begin with a
    # capital letter and cannot follow '/'.
    r"|(?<![/\w])patch\b|(?<![/\w])mock\b|\bAsyncMock\b"
    # Port 0 (ephemeral OS-assigned port) and positional 0 port arg.
    r"|port\s*0|, 0\)"
)


def _py_test_units(text: str):
    """Yield one text unit per `def test_`/`async def test_` function: its contiguous
    @-decorator/comment/blank lines + the def line + the indented body. Per-function
    scoping (Codex F3) prevents a gated or tmp_path SIBLING test from suppressing an
    ungated violating sibling in the same file (whole-file suppression would).
    Residual (advisory, harmless): a MODULE-LEVEL gate (top-level `pytestmark` /
    `pytest.importorskip`) is outside every test unit, so a module-gated violation
    may still surface a nudge — acceptable for an advisory (FP = harmless reminder)."""
    lines = text.splitlines()
    n = len(lines)
    i = 0
    while i < n:
        m = re.match(r"(\s*)(?:async\s+)?def\s+test_\w+", lines[i])
        if m:
            indent = len(m.group(1))
            j, decos = i - 1, []
            while j >= 0 and (lines[j].lstrip().startswith("@")
                              or lines[j].lstrip().startswith("#")
                              or lines[j].strip() == ""):
                decos.append(lines[j])
                j -= 1
            body, k = [lines[i]], i + 1
            while k < n:
                if lines[k].strip() and (len(lines[k]) - len(lines[k].lstrip())) <= indent:
                    break
                body.append(lines[k])
                k += 1
            yield "\n".join(reversed(decos)) + "\n" + "\n".join(body)
            i = k
            continue
        i += 1


def _detect_python(text: str) -> "C5Finding | None":
    # Per-test-function: a gated/tmp_path sibling must NOT suppress an ungated
    # violating sibling (whole-file scan would — Codex F3).
    for unit in _py_test_units(text):
        code = _strip_line_comments(unit, "#")  # whole-line comments only (see module note)
        m = _PY_PRECISE_OPEN.search(code)
        if not m:
            continue
        if _PY_GATE.search(code) or _PY_EPHEMERAL.search(code):
            continue
        return C5Finding(signature=m.group(0), lang="python")
    return None


def _c5_detect(text: str, lang: str) -> "C5Finding | None":
    """Dispatch to the per-language detector. Pure. May raise on malformed input."""
    if lang == "rust":
        return _detect_rust(text)
    if lang == "python":
        return _detect_python(text)
    return None
