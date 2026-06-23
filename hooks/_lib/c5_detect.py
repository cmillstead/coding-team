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
    #[...] lines) — NEVER the whole file. Scanning the whole file would treat a
    #[derive(...)]/#[allow(...)] on any unrelated struct as an 'unrecognized
    attribute' and suppress every violation in that file (near-total recall loss).
    The operator rule is 'unknown gate form ON THE TEST', so the unit must be scoped
    to the test's own attributes."""
    if _RUST_GATE_IGNORE.search(attr_text):
        return True
    if "cfg_attr" in attr_text and "ignore" in attr_text:
        return True
    if _RUST_GATE_CFG_FEATURE.search(attr_text):
        return True
    # CONSERVATIVE-GATE: any other #[...] attribute on THIS TEST that is not the
    # harmless #[test]/#[tokio::test]/#[rstest] attribute -> assume gated -> do not
    # fire (custom skip macro, unseen cfg_attr variant, #[should_panic], …).
    for m in re.finditer(r"#\[[^\]]*\]", attr_text):
        if _RUST_TEST_ATTR.search(m.group(0)):
            continue  # the test attribute itself is harmless
        return True   # an unrecognized attribute -> conservative gated
    return False


def _rust_test_units(text: str):
    """Yield (attr_block, body) per #[test]-anchored fn. attr_block = the contiguous
    attribute/comment/blank lines directly above the fn; body = the fn signature line
    through its brace-matched end. Per-function scoping is what makes the
    conservative-gate correct (a struct's #[derive] is in NO test unit's attr_block)."""
    lines = text.splitlines()
    n = len(lines)
    i = 0
    while i < n:
        if re.search(r"\bfn\s+\w+", lines[i]):
            j, attrs, saw_test = i - 1, [], False
            while j >= 0 and (lines[j].lstrip().startswith("#[")
                              or lines[j].lstrip().startswith("//")
                              or lines[j].strip() == ""):
                attrs.append(lines[j])
                if _RUST_TEST_ATTR.search(lines[j]):
                    saw_test = True
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


def _detect_rust(text: str) -> "C5Finding | None":
    # Per-test-function: scan THIS fn's attrs for gates, THIS fn's body for the open.
    for attrs, body in _rust_test_units(text):
        attrs_nc = _strip_line_comments(attrs, "//")   # commented-out gate != a gate
        body_nc = _strip_line_comments(body, "//")
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
    r"tmp_path|tmpdir|tempfile|TemporaryDirectory|NamedTemporaryFile"
    r"|:memory:|app=|mock|patch|AsyncMock|port\s*0|, 0\)"
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
