"""Tests for graduated_checks.py — registry of Codex-learning reminder checks.

Each test verifies runtime behavior via the actual check functions and dispatch.
No mocks — real function calls with real inputs.
"""

import sys
from pathlib import Path

import pytest

# Ensure hooks/ is on sys.path so `from _lib import graduated_checks` works
HOOKS_DIR = Path("/Users/cevin/.claude/skills/coding-team/hooks")
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from _lib.graduated_checks import CheckResult, check_c1_path_trust, dispatch, GRADUATED_CHECKS


# ---------------------------------------------------------------------------
# C1 signal detection — positive cases
# ---------------------------------------------------------------------------


class TestC1SignalDetection:
    """check_c1_path_trust fires on C1 signals in various file types."""

    def test_path_shaped_field_in_py_content(self):
        """A path-shaped identifier name in .py content triggers C1."""
        content = "def store(repoPath: str) -> None:\n    pass\n"
        result = check_c1_path_trust("Edit", {"file_path": "foo.py", "new_string": content})
        assert result is not None
        assert result.mode == "advisory"

    def test_path_shaped_field_in_rs_content(self):
        """A path-shaped identifier name in .rs content triggers C1."""
        content = "fn process(filePath: &str) -> Result<()> { Ok(()) }\n"
        result = check_c1_path_trust("Edit", {"file_path": "foo.rs", "new_string": content})
        assert result is not None
        assert result.mode == "advisory"

    def test_path_shaped_field_in_ts_content(self):
        """A path-shaped identifier name in .ts content triggers C1."""
        content = "interface Config { storagePath: string; }\n"
        result = check_c1_path_trust("Edit", {"file_path": "foo.ts", "new_string": content})
        assert result is not None
        assert result.mode == "advisory"

    def test_reason_contains_expected_text(self):
        """C1 reason contains the verbatim design-default phrase fragments."""
        content = "let pathPrefix = '/usr/local';\n"
        result = check_c1_path_trust("Edit", {"file_path": "foo.js", "new_string": content})
        assert result is not None
        # Reason must mention the key C1 concepts
        assert "identifier" in result.reason
        assert "contains('/')" in result.reason

    def test_path_call_path_resolve(self):
        """path.resolve call in content triggers C1."""
        content = "const abs = path.resolve(userInput);\n"
        result = check_c1_path_trust("Edit", {"file_path": "foo.js", "new_string": content})
        assert result is not None

    def test_path_call_open_paren(self):
        """open( call in content triggers C1."""
        content = "with open(filePath) as f:\n    data = f.read()\n"
        result = check_c1_path_trust("Edit", {"file_path": "foo.py", "new_string": content})
        assert result is not None

    def test_path_call_fs_double_colon(self):
        """fs:: pattern in Rust content triggers C1."""
        content = "let data = fs::read_to_string(&path)?;\n"
        result = check_c1_path_trust("Edit", {"file_path": "foo.rs", "new_string": content})
        assert result is not None

    def test_path_call_include_str(self):
        """include_str! macro in Rust triggers C1."""
        content = 'let src = include_str!("../data/schema.sql");\n'
        result = check_c1_path_trust("Edit", {"file_path": "foo.rs", "new_string": content})
        assert result is not None

    def test_path_call_path_constructor(self):
        """Path( constructor call triggers C1."""
        content = "p = Path(userInput)\n"
        result = check_c1_path_trust("Edit", {"file_path": "foo.py", "new_string": content})
        assert result is not None

    def test_path_call_join(self):
        """join( call triggers C1."""
        content = "const full = join(baseDir, relativePart);\n"
        result = check_c1_path_trust("Edit", {"file_path": "foo.ts", "new_string": content})
        assert result is not None

    def test_single_gate_contains_double_quotes(self):
        """.contains(\"/\") in content triggers C1."""
        content = 'if value.contains("/") { return true; }\n'
        result = check_c1_path_trust("Edit", {"file_path": "foo.rs", "new_string": content})
        assert result is not None

    def test_single_gate_contains_single_quotes(self):
        """.contains('/') in content triggers C1."""
        content = "if value.contains('/') { return true; }\n"
        result = check_c1_path_trust("Edit", {"file_path": "foo.rs", "new_string": content})
        assert result is not None

    def test_write_tool_uses_content_field(self):
        """For Write tool, reads from tool_input['content'] not 'new_string'."""
        content = "storagePath: string\n"
        # new_string absent — must use content
        result = check_c1_path_trust("Write", {"file_path": "foo.ts", "content": content})
        assert result is not None

    def test_write_tool_empty_content_returns_none(self):
        """For Write tool, empty content returns None even if new_string is present."""
        result = check_c1_path_trust(
            "Write",
            {"file_path": "foo.ts", "content": "", "new_string": "repoPath"},
        )
        # content is empty → no signal
        assert result is None


# ---------------------------------------------------------------------------
# Compound field name detection (silent-partial guard)
# ---------------------------------------------------------------------------


class TestCompoundFieldNames:
    """Each compound path-shaped name must individually match."""

    @pytest.mark.parametrize("name", ["repoPath", "filePath", "storagePath", "pathPrefix"])
    def test_compound_name_matches(self, name: str):
        """Every named compound variant triggers C1."""
        content = f"function handle({name}: string) {{}}\n"
        result = check_c1_path_trust("Edit", {"file_path": "foo.ts", "new_string": content})
        assert result is not None, f"Expected match for {name!r}, got None"


# ---------------------------------------------------------------------------
# Both quote styles for the single-gate contains check
# ---------------------------------------------------------------------------


class TestContainsQuoteStyles:
    """Both .contains(\"/\") and .contains('/') must match."""

    def test_double_quote_contains(self):
        content = 'if input.contains("/") { panic!() }\n'
        result = check_c1_path_trust("Edit", {"file_path": "check.rs", "new_string": content})
        assert result is not None

    def test_single_quote_contains(self):
        content = "if input.contains('/') { panic!() }\n"
        result = check_c1_path_trust("Edit", {"file_path": "check.rs", "new_string": content})
        assert result is not None


# ---------------------------------------------------------------------------
# Negative cases — no false positives
# ---------------------------------------------------------------------------


class TestNoSignal:
    """Content without C1 signals returns None."""

    def test_plain_python_function(self):
        content = "def greet(name: str) -> str:\n    return f'Hello {name}'\n"
        result = check_c1_path_trust("Edit", {"file_path": "foo.py", "new_string": content})
        assert result is None

    def test_empty_content(self):
        result = check_c1_path_trust("Edit", {"file_path": "foo.py", "new_string": ""})
        assert result is None

    def test_missing_content_key(self):
        result = check_c1_path_trust("Edit", {"file_path": "foo.py"})
        assert result is None

    def test_non_edit_write_tool(self):
        """For a tool that is not Edit or Write, no content → None."""
        result = check_c1_path_trust("Read", {"file_path": "foo.py"})
        assert result is None


# ---------------------------------------------------------------------------
# dispatch() aggregation — proves all-hit, not first-hit
# ---------------------------------------------------------------------------


class TestDispatchAggregation:
    """dispatch() collects ALL non-None results from ALL registered checks."""

    def test_no_signal_returns_empty_list(self):
        result = dispatch("Edit", {"file_path": "foo.py", "new_string": "x = 1\n"})
        assert result == []

    def test_c1_signal_returns_non_empty(self):
        result = dispatch("Edit", {"file_path": "foo.py", "new_string": "repoPath = x\n"})
        assert len(result) >= 1
        assert all(isinstance(r, CheckResult) for r in result)

    def test_two_synthetic_checks_both_fire(self):
        """Temporarily extend the registry with two always-match checks; dispatch returns both."""
        import _lib.graduated_checks as gc

        def always_advisory_a(tool_name: str, tool_input: dict) -> "CheckResult | None":
            return CheckResult(reason="synthetic-A", mode="advisory")

        def always_advisory_b(tool_name: str, tool_input: dict) -> "CheckResult | None":
            return CheckResult(reason="synthetic-B", mode="advisory")

        original_length = len(gc.GRADUATED_CHECKS)
        gc.GRADUATED_CHECKS.append(always_advisory_a)
        gc.GRADUATED_CHECKS.append(always_advisory_b)
        try:
            results = gc.dispatch("Edit", {"file_path": "foo.py", "new_string": "x = 1\n"})
        finally:
            # Restore registry regardless of failure
            del gc.GRADUATED_CHECKS[original_length:]

        reasons = [r.reason for r in results]
        assert "synthetic-A" in reasons, f"synthetic-A missing from {reasons!r}"
        assert "synthetic-B" in reasons, f"synthetic-B missing from {reasons!r}"

    def test_synthetic_block_mode_check(self):
        """A block-mode check returns CheckResult with mode=='block'."""
        import _lib.graduated_checks as gc

        def block_check(tool_name: str, tool_input: dict) -> "CheckResult | None":
            return CheckResult(reason="block-reason", mode="block")

        original_length = len(gc.GRADUATED_CHECKS)
        gc.GRADUATED_CHECKS.append(block_check)
        try:
            results = gc.dispatch("Edit", {"file_path": "foo.py", "new_string": "x = 1\n"})
        finally:
            del gc.GRADUATED_CHECKS[original_length:]

        block_results = [r for r in results if r.mode == "block"]
        assert len(block_results) == 1
        assert block_results[0].reason == "block-reason"

    def test_dispatch_results_in_registry_order(self):
        """Results are returned in registry order (first-registered first)."""
        import _lib.graduated_checks as gc

        def check_first(tool_name: str, tool_input: dict) -> "CheckResult | None":
            return CheckResult(reason="first", mode="advisory")

        def check_second(tool_name: str, tool_input: dict) -> "CheckResult | None":
            return CheckResult(reason="second", mode="advisory")

        saved = gc.GRADUATED_CHECKS[:]
        gc.GRADUATED_CHECKS.clear()
        gc.GRADUATED_CHECKS.append(check_first)
        gc.GRADUATED_CHECKS.append(check_second)
        try:
            results = gc.dispatch("Edit", {"file_path": "foo.py", "new_string": "x\n"})
        finally:
            gc.GRADUATED_CHECKS[:] = saved

        assert [r.reason for r in results] == ["first", "second"]


# ---------------------------------------------------------------------------
# Regex correctness — every pattern compiles and each has a positive test
# ---------------------------------------------------------------------------


class TestRegexCompiles:
    """Import graduated_checks without error (all regex literals compiled at module level)."""

    def test_import_succeeds(self):
        import _lib.graduated_checks as gc
        # If any pattern failed to compile, the import itself would raise re.error
        assert gc is not None

    def test_field_name_pattern_has_positive_match(self):
        """The field-name regex matches at least one known identifier."""
        content = "filePath: string\n"
        result = check_c1_path_trust("Edit", {"file_path": "x.ts", "new_string": content})
        assert result is not None

    def test_path_call_pattern_has_positive_match(self):
        """The path-call patterns match at least one known call form."""
        content = "path.resolve(userInput)\n"
        result = check_c1_path_trust("Edit", {"file_path": "x.js", "new_string": content})
        assert result is not None

    def test_single_gate_pattern_has_positive_match(self):
        """The single-gate contains pattern matches at least one known form."""
        content = '.contains("/")\n'
        result = check_c1_path_trust("Edit", {"file_path": "x.rs", "new_string": content})
        assert result is not None


# ---------------------------------------------------------------------------
# Field-name regex boundary tests — locks case-sensitive token matching
# ---------------------------------------------------------------------------


class TestFieldNameRegexBoundary:
    """Pin the field-name regex: must fire on path-shaped identifiers,
    must NOT fire on common English words that merely contain a token
    as a mid-word substring (profile, report, directory, …).

    These tests lock the decision so breadth cannot silently regress.
    Content is crafted to contain ONLY the word under test — no path-call
    tokens and no .contains gate — so signal 1 is the only possible trigger.
    """

    # -- MUST fire ----------------------------------------------------------

    @pytest.mark.parametrize("identifier", [
        "repoPath",
        "filePath",
        "storagePath",
        "pathPrefix",
        # snake_case — token as leading component
        "file_path",
        "path",
        "rootDir",
        "srcDir",
        "destPath",
        # snake_case — token as TRAILING component (regression: \b missed these
        # because _ is a word char; fixed with (?<![A-Za-z]) lookbehind)
        "storage_path",
        "output_path",
        "dest_dir",
        "src_root",
    ])
    def test_must_fire_on_path_identifier(self, identifier: str):
        """Each path-shaped identifier triggers C1 via the field-name signal."""
        content = f"let {identifier} = value\n"
        result = check_c1_path_trust("Edit", {"file_path": "x.ts", "new_string": content})
        assert result is not None, (
            f"Expected C1 to fire on {identifier!r}, got None. "
            f"Field-name regex must match path-shaped identifiers."
        )

    # -- MUST NOT fire ------------------------------------------------------

    @pytest.mark.parametrize("word", [
        "profile",
        "report",
        "repository",
        "directory",
        "redirect",
        "destination",
        "destroy",
        "rootkit",
    ])
    def test_must_not_fire_on_common_english_word(self, word: str):
        """Common English words containing token substrings must NOT fire C1.

        Content contains only the word with no path-call tokens and no
        .contains gate, so the field-name regex is the only possible trigger.
        If these fire, the C1 reminder becomes noise and gets muted.
        """
        content = f"{word} = 1\n"
        result = check_c1_path_trust("Edit", {"file_path": "x.py", "new_string": content})
        assert result is None, (
            f"Expected no C1 match for {word!r} (false positive), got {result!r}. "
            f"Field-name regex must not fire on mid-word token substrings."
        )
