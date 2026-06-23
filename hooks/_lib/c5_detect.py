# skills/coding-team/hooks/_lib/c5_detect.py
"""C5 (test-hermeticity) pure detector — shared by the Rust block adapter
(git-safety-guard.py) and the Python advisory adapter (graduated_checks.py).

PURE: no I/O, no subprocess, no filesystem. Given test-file text + a language,
returns a finding describing a POSITIVELY-recognized ungated open against an
external/shared/non-ephemeral resource, or None.

CONSERVATIVE-GATE HARD RULE (operator condition 2): on ANY unrecognized,
ambiguous, or conditional attribute/macro present on the test, treat the test
as GATED and return None. Fail toward NOT-detecting, never toward detecting on
uncertainty. (This converts the open-ended gate-vocabulary completeness problem
from a dangerous false-positive into a tolerable false-negative.)

Gate scan strips WHOLE-LINE comments (`//` Rust, `#` Python) before the
gate/ephemeral test — this kills the comment-spoof FN the spike actually measured
(a gate token on its own comment line). INLINE comment tails (a real open with a
trailing `// tempfile` / `# tempfile`) are deliberately NOT stripped: a naive
inline strip would corrupt string literals containing the comment marker — every
`https://` URL contains `//`, and `#` can appear in a path/URL literal — which on
the BLOCKING Rust path risks breaking real-violation detection (the dangerous FP
direction). The inline-comment spoof therefore remains an accepted, fail-open-safe
FN (it suppresses a detection, never forces a false block) — disclosed in the
honest marker, owned by Codex review. (Codex F4.)

May raise on a malformed input; CALLERS (both adapters) wrap in try/except->None.
See c05-test-hermeticity.md and SPIKE-RESULTS.md.
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
# `tempfile` (bare) covers both `tempfile::tempdir(...)` and inline comment
# tails like `// tempfile` — the latter is an accepted fail-open-safe FN
# (Codex F4): we do not strip inline comments, so a trailing `// tempfile`
# suppresses detection rather than forcing a false block. This is intentional:
# inline-stripping risks corrupting `https://` string literals on the blocking path.
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
    unrelated struct as an 'unrecognized attribute' and suppress every violation in
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


def _rust_test_units(text: str):
    """Yield (attr_block, body) per #[test]-anchored fn. attr_block = the contiguous
    attribute/comment/blank lines directly above the fn; body = the fn signature line
    through its brace-matched end. Per-function scoping is what makes the
    conservative-gate correct (a struct's #[derive] is in NO test unit's attr_block).

    FIX 1: the upward walk now handles multiline attributes and block comments.
    Rustfmt may wrap a long ``#[cfg_attr(..., ignore)]`` across several lines;
    the continuation lines (``    not(...),``, ``    ignore``, ``)]``) do not start
    with ``#[``, so the original walk stopped prematurely and lost the gate.

    We use a "pending close debt" tracker going upward through source lines:
    - Going upward, a line with MORE `]`/`)` than `[`/`(` (net closing brackets)
      signals that there must be an unmatched open bracket ABOVE — we MUST keep
      walking upward to capture the full attribute.
    - ``close_debt`` accumulates unmatched closing brackets encountered so far;
      when it is > 0 we are "inside" a multiline attribute that spans above us.
    - Block-comment lines (``/* ... */``) between attrs are also collected so
      they do not break the walk.
    """
    lines = text.splitlines()
    n = len(lines)
    i = 0
    while i < n:
        if re.search(r"\bfn\s+\w+", lines[i]):
            j, attrs, saw_test = i - 1, [], False
            # close_debt > 0 means the lines collected so far (below in source
            # order) have more `]`/`)` than `[`/`(`, so there must be an
            # unmatched `#[`/`(` somewhere above — we must keep walking.
            close_debt = 0
            while j >= 0:
                line = lines[j]
                stripped = line.lstrip()
                # Net closes on this line (going upward, closes = debt we need
                # to resolve by finding matching opens above).
                line_opens = line.count("[") + line.count("(")
                line_closes = line.count("]") + line.count(")")
                net_closes = line_closes - line_opens   # positive = more closes

                # Include this line if:
                # (a) it is recognisably part of an attribute region, OR
                # (b) we still have unmatched closes from lines already collected
                #     (we are inside a multiline attribute), OR
                # (c) this line itself contributes unmatched closes (it is the
                #     closing half of a multiline attribute whose `#[` is above).
                is_attr_line = _is_attr_region_line(stripped)
                in_multiline = close_debt > 0
                starts_close = net_closes > 0   # e.g. the `)]` line

                if not (is_attr_line or in_multiline or starts_close):
                    break

                attrs.append(line)
                if _RUST_TEST_ATTR.search(line):
                    saw_test = True
                # Update close_debt: closes increase debt, opens reduce it.
                close_debt += net_closes
                if close_debt < 0:
                    close_debt = 0
                j -= 1
            if saw_test:
                depth, started, body, k = 0, False, [], i
                while k < n:
                    depth += lines[k].count("{") - lines[k].count("}")
                    body.append(lines[k])
                    if "{" in lines[k]:
                        started = True
                    if started and depth <= 0:
                        break
                    k += 1
                yield ("\n".join(reversed(attrs)), "\n".join(body))
                i = k + 1
                continue
        i += 1


# FIX 2: patterns to blank out string/char literal CONTENTS before applying
# _RUST_OPEN, so a signature inside a literal (error-message asserts, insta
# snapshots, raw strings) does not cause a false block.
#
# Order matters: raw strings before normal strings so the ``r``/``r#`` prefix is
# consumed as part of the raw-string token and not mistaken for an identifier.
# Char literals are handled after normal strings.
#
# The replacement is a single placeholder character so offsets don't shift in a
# way that would break surrounding code structure; we only need the PRESENCE of
# the open signature to be absent, not offset accuracy.
_RUST_RAW_STR = re.compile(
    r'r(#+)".*?"\1',   # r#"..."# / r##"..."## etc. — DOTALL not needed: we
    re.DOTALL          # scan per-function bodies which may span multiple lines.
)
_RUST_NORMAL_STR = re.compile(
    r'"(?:\\.|[^"\\])*"',
    re.DOTALL,
)
_RUST_CHAR_LITERAL = re.compile(
    r"'(?:\\.|[^'\\])'"
)


def _strip_rust_string_contents(text: str) -> str:
    """Replace the CONTENTS (not the delimiters) of Rust string/char literals
    with a placeholder so that open-signatures inside literals are invisible to
    _RUST_OPEN.  Raw strings are stripped first to avoid the ``r`` prefix being
    left behind and accidentally matching as an identifier.

    This is NOT a full Rust lexer — it is a conservative best-effort strip that
    handles the common cases (normal strings, r#...# raw strings, char literals).
    It is safe to over-strip (turns literal contents to placeholder): the only
    downstream consumer is _RUST_OPEN, and a placeholder never matches it.
    Inline-comment tails are left intact (documented Codex F4 FN — see module
    docstring)."""
    # 1. Raw strings (r"..." / r#"..."# / r##"..."## …)
    text = _RUST_RAW_STR.sub(lambda m: f'r{m.group(1)}"_"{m.group(1)}', text)
    # 2. Normal double-quoted strings
    text = _RUST_NORMAL_STR.sub('""', text)
    # 3. Char literals (single-quoted, one char or escape sequence)
    text = _RUST_CHAR_LITERAL.sub("'_'", text)
    return text


def _detect_rust(text: str) -> "C5Finding | None":
    # Per-test-function: scan THIS fn's attrs for gates, THIS fn's body for the open.
    for attrs, body in _rust_test_units(text):
        attrs_nc = _strip_line_comments(attrs, "//")   # commented-out gate != a gate
        body_nc = _strip_line_comments(body, "//")
        # FIX 2: strip string literal contents so open-signatures inside literals
        # (error-message asserts, insta snapshots) do not false-block.
        body_nc = _strip_rust_string_contents(body_nc)
        m = _RUST_OPEN.search(body_nc)
        if not m:
            continue
        if _rust_gated(attrs_nc):
            continue
        if _RUST_EPHEMERAL.search(body_nc):
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
