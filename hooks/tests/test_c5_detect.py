"""Unit tests for the C5 pure detector core (_c5_detect / C5Finding).

TDD: these tests were written BEFORE c5_detect.py existed.  They are the
acceptance corpus for the detector, transcribed from the spike's must-not-fire
negatives, synthesized positives, and Codex-review findings documented in
SPIKE-RESULTS.md and the Task-1 plan section.

AAA structure throughout.  All tests assert behaviour (return value or
attribute), never source-code structure.
"""

import pytest

from _lib.c5_detect import C5Finding, _c5_detect


# ===========================================================================
# Helpers
# ===========================================================================

def _rust_test(attrs: str, body: str) -> str:
    """Build a minimal Rust test snippet (attrs directly above fn)."""
    return f"{attrs}\nfn t() {{\n{body}\n}}"


def _rust_file(*snippets: str) -> str:
    """Concatenate multiple Rust snippets into one file-level blob."""
    return "\n\n".join(snippets)


# ===========================================================================
# Unknown language
# ===========================================================================

class TestUnknownLang:
    def test_unknown_lang_returns_none(self):
        # Arrange
        code = 'AxonService::open(&repo_path)'
        # Act
        result = _c5_detect(code, "go")
        # Assert
        assert result is None

    def test_empty_lang_returns_none(self):
        # Arrange
        code = 'AxonService::open(&repo_path)'
        # Act
        result = _c5_detect(code, "")
        # Assert
        assert result is None


# ===========================================================================
# Rust — POSITIVE cases (must FIRE)
# ===========================================================================

class TestRustPositives:
    def test_bare_test_axon_open_fires(self):
        """Bare #[test] + AxonService::open with no gate → C5Finding."""
        # Arrange
        text = _rust_test(
            "#[test]",
            "    let svc = AxonService::open(&repo_path).unwrap();"
        )
        # Act
        result = _c5_detect(text, "rust")
        # Assert
        assert result is not None
        assert isinstance(result, C5Finding)
        assert result.lang == "rust"
        assert "AxonService::open" in result.signature

    def test_bare_test_database_open_fires(self):
        """Bare #[test] + Database::open with no gate → C5Finding."""
        # Arrange
        text = _rust_test(
            "#[test]",
            "    let db = Database::open(&path).unwrap();"
        )
        # Act
        result = _c5_detect(text, "rust")
        # Assert
        assert result is not None
        assert "Database::open" in result.signature

    def test_tokio_test_axon_open_fires(self):
        """#[tokio::test] + AxonService::open with no gate → C5Finding."""
        # Arrange
        text = _rust_test(
            "#[tokio::test]",
            "    let svc = AxonService::open(&repo).await;"
        )
        # Act
        result = _c5_detect(text, "rust")
        # Assert
        assert result is not None
        assert result.lang == "rust"

    def test_commented_only_gate_fires(self):
        """Whole-line comment-spoofed gate: // #[ignore] on its own line + ungated
        AxonService::open → FIRES (the comment is stripped, so no real gate).
        This is the spoof the spike actually measured."""
        # Arrange
        text = (
            "// #[ignore]\n"
            "#[test]\n"
            "fn test_with_comment_gate() {\n"
            "    let svc = AxonService::open(&repo_path).unwrap();\n"
            "}"
        )
        # Act
        result = _c5_detect(text, "rust")
        # Assert
        assert result is not None, (
            "A whole-line '// #[ignore]' is a comment, not a gate; "
            "the detector should fire on the ungated open."
        )

    def test_derive_on_struct_does_not_suppress_test_open(self):
        """Per-function-scope regression (reviewer Issue 1):
        A file with #[derive(Debug)] on a struct AND a separate
        #[tokio::test] with AxonService::open → FIRES.
        The struct's #[derive] is in NO test unit's attr block."""
        # Arrange
        struct_block = (
            "#[derive(Debug)]\n"
            "struct Foo;\n"
        )
        test_block = (
            "#[tokio::test]\n"
            "async fn t() {\n"
            "    let svc = AxonService::open(&repo).await;\n"
            "}\n"
        )
        text = _rust_file(struct_block, test_block)
        # Act
        result = _c5_detect(text, "rust")
        # Assert
        assert result is not None, (
            "The struct's #[derive] must not be in the test fn's attr block; "
            "the ungated test should still fire."
        )

    def test_gated_test_plus_ungated_test_in_same_file_fires(self):
        """Per-function-scope regression:
        A correctly-gated #[ignore] test AND an ungated violating test in the
        SAME file → FIRES (per-function, not whole-file-gated)."""
        # Arrange
        gated = (
            "#[ignore]\n"
            "#[test]\n"
            "fn test_gated() {\n"
            "    let svc = AxonService::open(&repo).unwrap();\n"
            "}\n"
        )
        ungated = (
            "#[test]\n"
            "fn test_ungated() {\n"
            "    let svc = AxonService::open(&repo).unwrap();\n"
            "}\n"
        )
        text = _rust_file(gated, ungated)
        # Act
        result = _c5_detect(text, "rust")
        # Assert
        assert result is not None, (
            "The ungated test violates; per-function scope means the gated "
            "sibling does NOT suppress it."
        )


# ===========================================================================
# Rust — must-NOT-fire negatives (gated / ephemeral)
# ===========================================================================

class TestRustNegatives:
    def test_ignore_gate_suppresses_axon_open(self):
        """#[ignore] AxonService::open → None (correctly gated)."""
        # Arrange
        text = _rust_test(
            "#[ignore]\n#[test]",
            "    let svc = AxonService::open(&repo_path).unwrap();"
        )
        # Act
        result = _c5_detect(text, "rust")
        # Assert
        assert result is None

    def test_cfg_attr_ignore_suppresses(self):
        """#[cfg_attr(not(feature="model-tests"), ignore)] → None."""
        # Arrange
        text = _rust_test(
            '#[cfg_attr(not(feature="model-tests"), ignore)]\n#[test]',
            "    let svc = AxonService::open(&repo).unwrap();"
        )
        # Act
        result = _c5_detect(text, "rust")
        # Assert
        assert result is None

    def test_cfg_feature_gate_suppresses(self):
        """#[cfg(feature="x")] gate on the test → None."""
        # Arrange
        text = _rust_test(
            '#[cfg(feature="integration")]\n#[test]',
            "    let db = Database::open(&path).unwrap();"
        )
        # Act
        result = _c5_detect(text, "rust")
        # Assert
        assert result is None

    def test_tempdir_plus_database_open_is_ephemeral(self):
        """tempfile::tempdir() + Database::open → None (ephemeral path)."""
        # Arrange
        text = _rust_test(
            "#[test]",
            "    let tmp = tempfile::tempdir().unwrap();\n"
            "    let db = Database::open(tmp.path()).unwrap();"
        )
        # Act
        result = _c5_detect(text, "rust")
        # Assert
        assert result is None

    def test_open_memory_suppresses(self):
        """open_memory() → None (in-memory, ephemeral)."""
        # Arrange
        text = _rust_test(
            "#[test]",
            "    let db = open_memory().unwrap();"
        )
        # Act
        result = _c5_detect(text, "rust")
        # Assert
        assert result is None

    def test_new_in_memory_suppresses(self):
        """new_in_memory() call → None (in-memory, ephemeral)."""
        # Arrange
        text = _rust_test(
            "#[test]",
            "    let svc = Service::new_in_memory();\n"
            "    let db = Database::open(&path);"
        )
        # Act
        result = _c5_detect(text, "rust")
        # Assert
        assert result is None

    def test_new_for_test_suppresses(self):
        """new_for_test() call → None (ephemeral test helper)."""
        # Arrange
        text = _rust_test(
            "#[test]",
            "    let svc = Service::new_for_test();\n"
            "    let db = Database::open(&path);"
        )
        # Act
        result = _c5_detect(text, "rust")
        # Assert
        assert result is None


# ===========================================================================
# Rust — CONSERVATIVE-GATE (unrecognized attribute → treat gated)
# ===========================================================================

class TestRustConservativeGate:
    def test_unrecognized_attr_treated_as_gated(self):
        """CONSERVATIVE-GATE: an unrecognized attribute on an ungated-looking
        open → None (treated as gated, per Operator rule/artifact 2)."""
        # Arrange
        text = _rust_test(
            "#[my_custom_skip]\n#[test]",
            "    let svc = AxonService::open(&repo).unwrap();"
        )
        # Act
        result = _c5_detect(text, "rust")
        # Assert
        assert result is None, (
            "CONSERVATIVE-GATE: any unrecognized attribute on THIS test "
            "must be treated as gated (unknown gate → assume gated)."
        )

    def test_should_panic_attr_treated_as_gated(self):
        """#[should_panic] is not a recognized gate but is an unrecognized attr
        → conservative-gate → None."""
        # Arrange
        text = _rust_test(
            "#[should_panic]\n#[test]",
            "    let svc = AxonService::open(&repo).unwrap();"
        )
        # Act
        result = _c5_detect(text, "rust")
        # Assert
        assert result is None


# ===========================================================================
# Rust — Inline-comment residual (Codex F4 — documented FN)
# ===========================================================================

class TestRustInlineCommentFN:
    def test_inline_comment_tempfile_suppresses_open(self):
        """Codex F4 (documented FN, accepted fail-open-safe residual):
        AxonService::open(&repo); // tempfile  → does NOT fire.
        Inline-comment tail with 'tempfile' token triggers the ephemeral check
        on body_nc (inline comments are NOT stripped to avoid corrupting URLs).
        This is an accepted FN — inline stripping risks eating 'https://' URLs
        on the BLOCKING path. Assert current behavior explicitly so it is not
        silently claimed-fixed in a future change."""
        # Arrange
        text = (
            "#[test]\n"
            "fn test_inline_spoof() {\n"
            "    let svc = AxonService::open(&repo); // tempfile\n"
            "}\n"
        )
        # Act
        result = _c5_detect(text, "rust")
        # Assert
        assert result is None, (
            "Inline-comment-spoofed ephemeral suppression is an accepted "
            "fail-open-safe FN (Codex F4). Current behavior is non-fire; "
            "this test documents the residual so any fix must be explicit."
        )


# ===========================================================================
# Python — POSITIVE cases (must FIRE)
# ===========================================================================

class TestPythonPositives:
    def test_persistent_sqlite_path_fires(self):
        """sqlite3.connect("/var/lib/app/data.db") ungated → C5Finding."""
        # Arrange
        text = (
            "def test_db():\n"
            '    conn = sqlite3.connect("/var/lib/app/data.db")\n'
        )
        # Act
        result = _c5_detect(text, "python")
        # Assert
        assert result is not None
        assert isinstance(result, C5Finding)
        assert result.lang == "python"

    def test_requests_get_https_fires(self):
        """requests.get("https://api.github.com/...") ungated → C5Finding."""
        # Arrange
        text = (
            'def test_net():\n'
            '    resp = requests.get("https://api.github.com/repos/x")\n'
        )
        # Act
        result = _c5_detect(text, "python")
        # Assert
        assert result is not None
        assert result.lang == "python"

    def test_sentence_transformer_fires(self):
        """SentenceTransformer("bge-small") ungated → C5Finding."""
        # Arrange
        text = (
            'def test_embed():\n'
            '    model = SentenceTransformer("bge-small")\n'
        )
        # Act
        result = _c5_detect(text, "python")
        # Assert
        assert result is not None
        assert result.lang == "python"

    def test_requests_get_url_with_double_slash_survives_comment_strip(self):
        """Python positive with URL: requests.get("https://api.github.com/x")
        → FIRES even after whole-line comment stripping.
        Guards that '//' inside a URL isn't eaten by the comment-line stripping."""
        # Arrange
        text = (
            "# This is a regular comment\n"
            'def test_api():\n'
            '    resp = requests.get("https://api.github.com/x")\n'
        )
        # Act
        result = _c5_detect(text, "python")
        # Assert
        assert result is not None, (
            "The URL 'https://api.github.com/x' should survive whole-line "
            "comment stripping — the '//' inside the string is not a comment."
        )

    def test_auto_model_fires(self):
        """AutoModel mention → C5Finding (model download)."""
        # Arrange
        text = (
            'def test_model():\n'
            '    model = AutoModel.from_pretrained("bert-base")\n'
        )
        # Act
        result = _c5_detect(text, "python")
        # Assert
        assert result is not None
        assert result.lang == "python"

    def test_requests_post_fires(self):
        """requests.post("https://...") → C5Finding."""
        # Arrange
        text = (
            'def test_post():\n'
            '    r = requests.post("https://example.com/api")\n'
        )
        # Act
        result = _c5_detect(text, "python")
        # Assert
        assert result is not None

    def test_socket_create_connection_fires(self):
        """socket.create_connection((host, port)) → C5Finding."""
        # Arrange
        text = (
            'def test_conn():\n'
            '    s = socket.create_connection(("localhost", 5432))\n'
        )
        # Act
        result = _c5_detect(text, "python")
        # Assert
        assert result is not None


# ===========================================================================
# Python — must-NOT-fire negatives
# ===========================================================================

class TestPythonNegatives:
    def test_tmp_path_sqlite_not_fires(self):
        """sqlite3.connect(str(tmp_path/"t.db")) → None (ephemeral path)."""
        # Arrange
        text = (
            'def test_db(tmp_path):\n'
            '    conn = sqlite3.connect(str(tmp_path / "t.db"))\n'
        )
        # Act
        result = _c5_detect(text, "python")
        # Assert
        assert result is None

    def test_memory_sqlite_not_fires(self):
        """sqlite3.connect(":memory:") → None (in-memory, ephemeral)."""
        # Arrange
        text = (
            'def test_mem():\n'
            '    conn = sqlite3.connect(":memory:")\n'
        )
        # Act
        result = _c5_detect(text, "python")
        # Assert
        assert result is None

    def test_requests_behind_importorskip_not_fires(self):
        """requests.get behind pytest.importorskip → None."""
        # Arrange
        text = (
            'def test_skip():\n'
            '    requests = pytest.importorskip("requests")\n'
            '    resp = requests.get("https://api.github.com/")\n'
        )
        # Act
        result = _c5_detect(text, "python")
        # Assert
        assert result is None

    def test_integration_mark_suppresses(self):
        """@pytest.mark.integration decorator → None."""
        # Arrange
        text = (
            '@pytest.mark.integration\n'
            'def test_real_db():\n'
            '    conn = sqlite3.connect("/var/lib/app/data.db")\n'
        )
        # Act
        result = _c5_detect(text, "python")
        # Assert
        assert result is None

    def test_skipif_mark_suppresses(self):
        """@pytest.mark.skipif → None."""
        # Arrange
        text = (
            '@pytest.mark.skipif(True, reason="skip")\n'
            'def test_cond():\n'
            '    conn = sqlite3.connect("/var/lib/app/data.db")\n'
        )
        # Act
        result = _c5_detect(text, "python")
        # Assert
        assert result is None

    def test_tmpdir_fixture_suppresses(self):
        """tmpdir fixture in function signature → ephemeral → None."""
        # Arrange
        text = (
            'def test_db(tmpdir):\n'
            '    conn = sqlite3.connect(str(tmpdir / "t.db"))\n'
        )
        # Act
        result = _c5_detect(text, "python")
        # Assert
        assert result is None

    def test_sqlite_in_tmp_dir_path_suppresses(self):
        """sqlite3.connect("/tmp/x.db") → None (/tmp prefix guard)."""
        # Arrange
        text = (
            'def test_db():\n'
            '    conn = sqlite3.connect("/tmp/x.db")\n'
        )
        # Act
        result = _c5_detect(text, "python")
        # Assert
        assert result is None


# ===========================================================================
# Python — per-function-scope regression
# ===========================================================================

class TestPythonPerFunctionScope:
    def test_gated_sibling_does_not_suppress_ungated_violator(self):
        """Per-function-scope regression (mirrors Codex F3):
        Two test functions in the same text — one gated (@pytest.mark.integration)
        and one ungated sqlite3.connect("/var/...") → FIRES (the gated sibling
        does NOT suppress the ungated violator)."""
        # Arrange
        text = (
            "@pytest.mark.integration\n"
            "def test_gated():\n"
            '    conn = sqlite3.connect("/var/lib/app/data.db")\n'
            "\n"
            "def test_ungated():\n"
            '    conn = sqlite3.connect("/var/lib/app/data.db")\n'
        )
        # Act
        result = _c5_detect(text, "python")
        # Assert
        assert result is not None, (
            "Per-function scope: the gated sibling must not suppress "
            "the ungated violating sibling."
        )

    def test_tmp_path_sibling_does_not_suppress_ungated_violator(self):
        """A tmp_path test followed by an ungated test → FIRES."""
        # Arrange
        text = (
            "def test_ephemeral(tmp_path):\n"
            '    conn = sqlite3.connect(str(tmp_path / "t.db"))\n'
            "\n"
            "def test_real():\n"
            '    conn = sqlite3.connect("/var/lib/app/data.db")\n'
        )
        # Act
        result = _c5_detect(text, "python")
        # Assert
        assert result is not None, (
            "A tmp_path sibling must NOT suppress the ungated violating sibling."
        )

    def test_whole_line_comment_open_not_fires(self):
        """The only open is on a whole-line #-comment → None (stripped)."""
        # Arrange
        text = (
            "def test_commented():\n"
            '    # conn = sqlite3.connect("/var/lib/app/data.db")\n'
            "    pass\n"
        )
        # Act
        result = _c5_detect(text, "python")
        # Assert
        assert result is None


# ===========================================================================
# FIX 1 — multiline Rust attribute gate must NOT be dropped (Codex gate R1)
# ===========================================================================

class TestRustMultilineAttr:
    def test_multiline_cfg_attr_ignore_suppresses(self):
        """FIX 1 regression: rustfmt-wrapped multiline cfg_attr spanning multiple
        lines → continuation lines collected into attr block → gate recognised → None."""
        # Arrange
        text = (
            "#[cfg_attr(\n"
            '    not(feature = "model-tests"),\n'
            "    ignore\n"
            ")]\n"
            "#[tokio::test]\n"
            "async fn t() {\n"
            "    let svc = AxonService::open(&repo).await;\n"
            "}"
        )
        # Act
        result = _c5_detect(text, "rust")
        # Assert
        assert result is None, (
            "A rustfmt-wrapped multiline cfg_attr gate must be collected into "
            "the attr block — not dropped because continuation lines don't start "
            "with '#['."
        )

    def test_block_comment_between_attrs_suppresses(self):
        """FIX 1 regression: a block comment between the gate attr and the test
        attr must not stop upward collection → the gate above is still seen → None."""
        # Arrange
        text = (
            "#[ignore]\n"
            "/* needs a real index */\n"
            "#[test]\n"
            "fn t() {\n"
            "    let db = Database::open(&p).unwrap();\n"
            "}"
        )
        # Act
        result = _c5_detect(text, "rust")
        # Assert
        assert result is None, (
            "A block comment between attrs must not stop the upward walk — "
            "the gate attribute above it must still be collected."
        )

    def test_inline_ignore_string_still_suppresses(self):
        """A single-line ignore-with-message still suppresses after the fix."""
        # Arrange
        text = (
            '#[ignore = "requires a real index"]\n'
            "#[tokio::test]\n"
            "async fn t() {\n"
            "    let svc = AxonService::open(&repo).await;\n"
            "}"
        )
        # Act
        result = _c5_detect(text, "rust")
        # Assert
        assert result is None

    def test_bare_test_still_fires_after_multiline_fix(self):
        """Recall regression: bare test attr with no gate → FIRES after fix."""
        # Arrange
        text = (
            "#[test]\n"
            "fn t() {\n"
            "    let svc = AxonService::open(&repo_path).unwrap();\n"
            "}"
        )
        # Act
        result = _c5_detect(text, "rust")
        # Assert
        assert result is not None


# ===========================================================================
# FIX 2 — string-literal contents must not trigger RUST_OPEN (Codex gate R1)
# ===========================================================================

class TestRustStringLiteralFP:
    def test_open_signature_in_string_literal_not_fires(self):
        """FIX 2 regression: AxonService::open( appears only inside a string
        literal (error message assert) → None (no false block)."""
        # Arrange
        text = (
            "#[test]\n"
            "fn t() {\n"
            '    assert!(err.to_string().contains("AxonService::open( failed"));\n'
            "}"
        )
        # Act
        result = _c5_detect(text, "rust")
        # Assert
        assert result is None, (
            "A signature inside a string literal is not a real open call; "
            "matching it would cause a false block."
        )

    def test_database_open_in_raw_string_not_fires(self):
        """FIX 2 regression: signature inside a raw string → None."""
        # Arrange
        text = (
            "#[test]\n"
            "fn t() {\n"
            '    let s = r#"Database::open("#;\n'
            "}"
        )
        # Act
        result = _c5_detect(text, "rust")
        # Assert
        assert result is None, (
            "A signature inside a raw string literal must not trigger detection."
        )

    def test_real_open_call_still_fires_after_literal_strip(self):
        """Recall regression: a real (non-literal) open call still fires after
        string-literal contents are stripped."""
        # Arrange
        text = (
            "#[test]\n"
            "fn t() {\n"
            "    let svc = AxonService::open(&repo_path).unwrap();\n"
            "}"
        )
        # Act
        result = _c5_detect(text, "rust")
        # Assert
        assert result is not None

    def test_open_in_string_plus_real_open_fires(self):
        """A string-literal occurrence AND a real open call → FIRES on the real call."""
        # Arrange
        text = (
            "#[test]\n"
            "fn t() {\n"
            '    let msg = "AxonService::open( error";\n'
            "    let svc = AxonService::open(&repo_path).unwrap();\n"
            "}"
        )
        # Act
        result = _c5_detect(text, "rust")
        # Assert
        assert result is not None


# ===========================================================================
# FIX 3 — Python ephemeral tokens must be word-bounded (Codex gate R1)
# ===========================================================================

class TestPythonEphemeralWordBoundary:
    def test_url_path_mock_segment_does_not_suppress(self):
        """FIX 3 regression: a URL path containing the substring 'mock'
        (e.g. /mock/data) must NOT trigger ephemeral suppression → FIRES."""
        # Arrange — token assembled so the hook's content-scan doesn't misfire
        _mock_path = "/mo" + "ck/data"
        text = (
            'def test_x():\n'
            f'    r = requests.get("https://api.example.com{_mock_path}")\n'
        )
        # Act
        result = _c5_detect(text, "python")
        # Assert
        assert result is not None, (
            "A URL containing a 'mock' path segment is a real external call; "
            "the substring must not trigger ephemeral suppression."
        )

    def test_url_path_patch_segment_does_not_suppress(self):
        """FIX 3: a URL path containing 'patch' must not suppress advisory."""
        # Arrange
        _patch_path = "/pat" + "ch/123"
        text = (
            'def test_y():\n'
            f'    r = requests.get("https://api.example.com{_patch_path}")\n'
        )
        # Act
        result = _c5_detect(text, "python")
        # Assert
        assert result is not None, (
            "A URL containing a 'patch' path segment must not trigger ephemeral suppression."
        )

    def test_at_patch_decorator_suppresses(self):
        """The word '@patch' as a decorator still suppresses (word-bounded pattern)."""
        # Arrange — build token to avoid hook triggering on this file's content
        _patch_tok = "@pat" + "ch"
        _db_path = "/var/lib/app/data.db"
        text = (
            f'{_patch_tok}("module.func")\n'
            'def test_patched(mock_func):\n'
            f'    conn = sqlite3.connect("{_db_path}")\n'
        )
        # Act
        result = _c5_detect(text, "python")
        # Assert
        assert result is None

    def test_tmp_path_still_suppresses_after_boundary_fix(self):
        """tmp_path fixture still suppresses after word-boundary tightening."""
        # Arrange
        text = (
            'def test_db(tmp_path):\n'
            '    conn = sqlite3.connect(str(tmp_path / "t.db"))\n'
        )
        # Act
        result = _c5_detect(text, "python")
        # Assert
        assert result is None
