"""
Tests for build-digest.py

Uses real temp directories (tmp_path), no mocks. AAA pattern throughout.
"""

import importlib.util
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_entry(
    entries_dir: Path,
    entry_id: str,
    design_default: str | None = None,
    filename: str | None = None,
) -> Path:
    """Write a minimal entry file to entries_dir.

    The canonical ID comes from the ``# <ID>`` H1 heading, NOT the filename.
    ``entry_id`` (e.g. ``p01``, ``c10``) becomes the heading ``# P01`` / ``# C10``.
    ``filename`` overrides the on-disk name (defaults to ``<entry_id>-some-slug.md``)
    so tests can exercise timestamp-named files whose ID lives only in the heading.
    """
    lines = [
        f"# {entry_id.upper()}",
        "",
        "| ID | Pattern | Check before dispatch |",
        "|----|---------|----------------------|",
        f"| {entry_id} | Some pattern | Some check |",
        "",
    ]
    if design_default is not None:
        lines.append(f"**Design default:** {design_default}")
    content = "\n".join(lines) + "\n"
    name = filename if filename is not None else f"{entry_id}-some-slug.md"
    path = entries_dir / name
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------
_SCRIPT = Path(__file__).parent / "build-digest.py"
_spec = importlib.util.spec_from_file_location("build_digest", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

render_digest = _mod.render_digest
write = _mod.write
check = _mod.check
main = _mod.main
EXIT_OK = _mod.EXIT_OK
EXIT_DIGEST_PROBLEM = _mod.EXIT_DIGEST_PROBLEM
FACE_DESIGN = _mod.FACE_DESIGN
FACE_REVIEW = _mod.FACE_REVIEW


# ---------------------------------------------------------------------------
# Test 1 — entry WITH a Design default appears in the rendered digest
# ---------------------------------------------------------------------------
def test_entry_with_design_default_appears_in_digest(tmp_path):
    """An entry containing a Design default produces the correct bullet in the digest."""
    # Arrange
    _write_entry(tmp_path, "p01", "Verify every symbol the plan names exists in the codebase.")

    # Act
    text, errors = render_digest(tmp_path)

    # Assert
    assert errors == []
    assert "**P1:** Verify every symbol the plan names exists in the codebase." in text


# ---------------------------------------------------------------------------
# Test 2 — GAP: entry with NO Design default causes non-zero exit, no file written
# ---------------------------------------------------------------------------
def test_gap_entry_causes_digest_problem_exit_and_no_digest_written(tmp_path):
    """An entry missing its Design default line returns EXIT_DIGEST_PROBLEM (3) and prevents the digest."""
    # Arrange
    _write_entry(tmp_path, "p01", design_default=None)  # no Design default
    digest_path = tmp_path / "digest.md"

    # Act
    result = write(tmp_path, digest_path)

    # Assert — dedicated digest-problem code (3), not Python's crash code (1), and digest NOT written
    assert result == EXIT_DIGEST_PROBLEM
    assert not digest_path.exists()


def test_gap_entry_is_reported_in_errors(tmp_path):
    """render_digest returns the offending entry ID in the errors list for a gap."""
    # Arrange
    _write_entry(tmp_path, "c01", design_default=None)

    # Act
    _, errors = render_digest(tmp_path)

    # Assert
    assert len(errors) == 1
    assert "GAP" in errors[0]
    assert "c01" in errors[0].lower() or "C1" in errors[0]


# ---------------------------------------------------------------------------
# Test 3 — DUPLICATE: entry with TWO Design default lines causes non-zero exit
# ---------------------------------------------------------------------------
def test_duplicate_design_defaults_causes_digest_problem_exit(tmp_path):
    """An entry with two Design default lines is rejected with EXIT_DIGEST_PROBLEM (never takes the first)."""
    # Arrange
    content = (
        "# P01\n\n"
        "| ID | Pattern | Check before dispatch |\n"
        "|----|---------|----------------------|\n"
        "| P1 | Some pattern | Some check |\n\n"
        "**Design default:** First sentence here.\n\n"
        "**Design default:** Second sentence here.\n"
    )
    (tmp_path / "p01-slug.md").write_text(content, encoding="utf-8")
    digest_path = tmp_path / "digest.md"

    # Act
    result = write(tmp_path, digest_path)

    # Assert — dedicated digest-problem code (3) and digest NOT written
    assert result == EXIT_DIGEST_PROBLEM
    assert not digest_path.exists()


def test_duplicate_design_defaults_reported_in_errors(tmp_path):
    """render_digest returns the DUPLICATE error for an entry with 2 Design default lines."""
    # Arrange
    content = (
        "# C02\n\n"
        "| ID | Pattern | Check |\n"
        "|----|---------|------|\n"
        "| C2 | A | B |\n\n"
        "**Design default:** Sentence one.\n\n"
        "**Design default:** Sentence two.\n"
    )
    (tmp_path / "c02-slug.md").write_text(content, encoding="utf-8")

    # Act
    _, errors = render_digest(tmp_path)

    # Assert
    assert len(errors) == 1
    assert "DUPLICATE" in errors[0]


# ---------------------------------------------------------------------------
# Test 3a — DUPLICATE CANONICAL ID: two DIFFERENT files both headed `# C10`
# (timestamp filenames) is ambiguous → deterministic error, exit 3, no write.
# ---------------------------------------------------------------------------
def test_duplicate_canonical_id_reported_in_errors(tmp_path):
    """Two distinct files claiming the same `# C10` heading surface a DUPLICATE ID error."""
    # Arrange — distinct filenames, identical canonical heading.
    _write_entry(tmp_path, "c10", "First sentence.", filename="20260620-100000-aaaa-first.md")
    _write_entry(tmp_path, "c10", "Second sentence.", filename="20260620-110000-bbbb-second.md")

    # Act
    text, errors = render_digest(tmp_path)

    # Assert — render suppressed; the duplicate ID and both filenames are named.
    assert text == ""
    dup_errors = [e for e in errors if "DUPLICATE ID" in e]
    assert len(dup_errors) == 1, errors
    assert "C10" in dup_errors[0]
    assert "20260620-100000-aaaa-first.md" in dup_errors[0]
    assert "20260620-110000-bbbb-second.md" in dup_errors[0]


def test_duplicate_canonical_id_causes_digest_problem_exit_and_no_digest_written(tmp_path):
    """Duplicate `# C10` across two files returns EXIT_DIGEST_PROBLEM (3) and writes no digest."""
    # Arrange
    _write_entry(tmp_path, "c10", "First sentence.", filename="20260620-100000-aaaa-first.md")
    _write_entry(tmp_path, "c10", "Second sentence.", filename="20260620-110000-bbbb-second.md")
    digest_path = tmp_path / "digest.md"

    # Act
    result = write(tmp_path, digest_path)

    # Assert
    assert result == EXIT_DIGEST_PROBLEM
    assert not digest_path.exists()


# ---------------------------------------------------------------------------
# Test 3b — MALFORMED/MISSING HEADING: an entry whose H1 isn't <p|c><digits>
# surfaces an error, returns EXIT_DIGEST_PROBLEM, and writes no digest. The
# canonical ID comes from the heading, so a missing/bad heading is the error
# (the FILENAME is irrelevant — see the timestamp-named test below).
# ---------------------------------------------------------------------------
def test_bad_heading_is_reported_in_errors(tmp_path):
    """An entry whose H1 heading is not '# <P|C><digits>' surfaces a MALFORMED error."""
    # Arrange — a real entry body and a perfectly fine filename, but the H1
    # heading is not a canonical P/C id.
    content = (
        "# Not An Id Heading\n\n"
        "| ID | Pattern | Check |\n"
        "|----|---------|------|\n"
        "| X | A | B |\n\n"
        "**Design default:** Valid body, but the H1 heading is not a P/C id.\n"
    )
    (tmp_path / "c01-good-filename.md").write_text(content, encoding="utf-8")

    # Act
    text, errors = render_digest(tmp_path)

    # Assert — the malformed heading is surfaced and the render is suppressed.
    assert text == ""
    assert len(errors) == 1
    assert "MALFORMED" in errors[0]
    assert "c01-good-filename.md" in errors[0]


def test_missing_heading_causes_digest_problem_exit_and_no_digest_written(tmp_path):
    """An entry with NO valid P/C heading returns EXIT_DIGEST_PROBLEM (3) and writes no digest."""
    # Arrange — no H1 heading at all (just a body + Design default).
    content = (
        "Some prose with no heading.\n\n"
        "**Design default:** No heading means no canonical id.\n"
    )
    (tmp_path / "20260620-120000-ffff-no-heading.md").write_text(content, encoding="utf-8")
    digest_path = tmp_path / "digest.md"

    # Act
    result = write(tmp_path, digest_path)

    # Assert — dedicated digest-problem code (3), and digest NOT written.
    assert result == EXIT_DIGEST_PROBLEM
    assert not digest_path.exists()


# ---------------------------------------------------------------------------
# Test 3c — TIMESTAMP-NAMED FILE: a drop-folder entry whose filename carries NO
# P/C prefix is included and ordered by its HEADING id, not its filename.
# ---------------------------------------------------------------------------
def test_timestamp_named_file_ordered_by_heading_id(tmp_path):
    """A timestamp-named file with heading '# C20' is included and ordered by C20."""
    # Arrange — a normal C2 entry plus a timestamp-named C20 entry (no p/c stem).
    _write_entry(tmp_path, "c2", "Sentence for C2.")
    _write_entry(
        tmp_path,
        "c20",
        "Sentence for C20.",
        filename="20260620-120000-ab12-foo.md",
    )

    # Act
    text, errors = render_digest(tmp_path)

    # Assert — both included, C20 derived from heading, ordered numerically after C2.
    assert errors == []
    assert "**C20:** Sentence for C20." in text
    pos_c2 = text.index("**C2:**")
    pos_c20 = text.index("**C20:**")
    assert pos_c2 < pos_c20, "C20 (from heading) must order numerically after C2"


# ---------------------------------------------------------------------------
# Test 4 — Determinism: rendering twice produces byte-identical output
# ---------------------------------------------------------------------------
def test_rendering_twice_is_byte_identical(tmp_path):
    """render_digest called twice on the same entries_dir produces identical output."""
    # Arrange
    _write_entry(tmp_path, "p01", "Always check symbols first.")
    _write_entry(tmp_path, "c01", "Validate path tiers carefully.")

    # Act
    text1, errors1 = render_digest(tmp_path)
    text2, errors2 = render_digest(tmp_path)

    # Assert
    assert errors1 == []
    assert errors2 == []
    assert text1 == text2


# ---------------------------------------------------------------------------
# Test 5 — Ordering (numeric-aware): c2 appears BEFORE c10 (not lexicographic)
# ---------------------------------------------------------------------------
def test_numeric_aware_ordering_c2_before_c10(tmp_path):
    """c2 must sort before c10 numerically (2 < 10), not lexicographically ("10" < "2").

    Both entries use timestamp filenames whose lexical order is the REVERSE of the
    correct heading-id order, proving the sort key is the HEADING id, not the name.
    """
    # Arrange — filename order (00... before 99...) is the opposite of id order.
    _write_entry(tmp_path, "c10", "Sentence for C10.", filename="00000000-000000-aaaa-ten.md")
    _write_entry(tmp_path, "c2", "Sentence for C2.", filename="99999999-999999-bbbb-two.md")

    # Act
    text, errors = render_digest(tmp_path)

    # Assert
    assert errors == []
    pos_c2 = text.index("**C2:**")
    pos_c10 = text.index("**C10:**")
    assert pos_c2 < pos_c10, (
        f"C2 (pos {pos_c2}) must appear before C10 (pos {pos_c10}) — numeric sort required"
    )


# ---------------------------------------------------------------------------
# Test 6 — _header.md is EXCLUDED from the digest
# ---------------------------------------------------------------------------
def test_header_md_is_excluded(tmp_path):
    """_header.md in the entries dir is never included in the digest output."""
    # Arrange — header with a Design default line (should still be excluded)
    header = tmp_path / "_header.md"
    header.write_text(
        "# Header\n\n**Design default:** This should NOT appear.\n",
        encoding="utf-8",
    )
    _write_entry(tmp_path, "p01", "Legitimate entry sentence.")

    # Act
    text, errors = render_digest(tmp_path)

    # Assert
    assert errors == []
    assert "This should NOT appear" not in text
    assert "P1" in text


# ---------------------------------------------------------------------------
# Test 7 — Normalization: LF only, no trailing spaces, exactly one trailing newline
# ---------------------------------------------------------------------------
def test_output_normalization(tmp_path):
    """Output uses LF-only endings, no trailing spaces per line, exactly one trailing newline."""
    # Arrange
    _write_entry(tmp_path, "p01", "No trailing space.  ")  # trailing spaces in source — stripped
    _write_entry(tmp_path, "c01", "Another sentence.")

    # Act
    text, errors = render_digest(tmp_path)

    # Assert
    assert errors == []
    # LF-only (no CRLF, no bare CR)
    assert "\r" not in text
    # No trailing spaces on any line
    for line in text.split("\n"):
        assert line == line.rstrip(), f"Line has trailing spaces: {line!r}"
    # Exactly one trailing newline
    assert text.endswith("\n")
    assert not text.endswith("\n\n")


# ---------------------------------------------------------------------------
# Test 8 — --check: in-sync → exit 0; diverged → exit non-zero + diff produced
#
# NOTE: The digest file MUST live outside the entries_dir; if it were placed
# inside, render_digest would attempt to parse "digest.md" as an entry and
# fail (its H1 heading is not a '# <P|C><digits>' canonical id).
# ---------------------------------------------------------------------------
def test_check_exits_zero_when_digest_matches(tmp_path):
    """--check exits 0 when the committed digest matches the rendered output."""
    # Arrange — entries in a subdirectory, digest alongside it
    entries_dir = tmp_path / "entries"
    entries_dir.mkdir()
    _write_entry(entries_dir, "p01", "Sentence for check test.")
    digest_path = tmp_path / "digest.md"
    # First write the digest so it exists
    rc = write(entries_dir, digest_path)
    assert rc == EXIT_OK

    # Act
    result = check(entries_dir, digest_path)

    # Assert — in sync stays EXIT_OK (0)
    assert result == EXIT_OK


def test_check_exits_nonzero_when_digest_diverges(tmp_path, capsys):
    """--check exits non-zero and emits a diff to stderr when entries diverge from digest."""
    # Arrange — entries in a subdirectory, digest alongside it
    entries_dir = tmp_path / "entries"
    entries_dir.mkdir()
    _write_entry(entries_dir, "p01", "Original sentence.")
    digest_path = tmp_path / "digest.md"
    write(entries_dir, digest_path)

    # Mutate the entry (change its Design default)
    (entries_dir / "p01-some-slug.md").write_text(
        "# P01\n\n"
        "| ID | Pattern | Check |\n"
        "|----|---------|------|\n"
        "| P1 | X | Y |\n\n"
        "**Design default:** Changed sentence.\n",
        encoding="utf-8",
    )

    # Act
    result = check(entries_dir, digest_path)
    captured = capsys.readouterr()

    # Assert — drift returns the dedicated digest-problem code (3), not 1
    assert result == EXIT_DIGEST_PROBLEM
    assert len(captured.err) > 0, "Expected a diff on stderr"


def test_check_exits_digest_problem_when_digest_missing(tmp_path):
    """--check returns EXIT_DIGEST_PROBLEM (3) when the digest file does not exist."""
    # Arrange — entries in a subdirectory
    entries_dir = tmp_path / "entries"
    entries_dir.mkdir()
    _write_entry(entries_dir, "p01", "Some sentence.")
    digest_path = tmp_path / "nonexistent-digest.md"

    # Act
    result = check(entries_dir, digest_path)

    # Assert — dedicated digest-problem code (3)
    assert result == EXIT_DIGEST_PROBLEM


# ---------------------------------------------------------------------------
# Test 9 — Grouping: P entries under P section, C under C, P section before C
# ---------------------------------------------------------------------------
def test_grouping_p_before_c_correct_sections(tmp_path):
    """P entries render under ## P, C entries under ## C, and P section precedes C section."""
    # Arrange
    _write_entry(tmp_path, "c01", "Code entry sentence.")
    _write_entry(tmp_path, "p01", "Plan entry sentence.")

    # Act
    text, errors = render_digest(tmp_path)

    # Assert
    assert errors == []

    # Both section headers present
    assert "## P — Plan defaults" in text
    assert "## C — Code defaults" in text

    # P section appears before C section
    pos_p = text.index("## P — Plan defaults")
    pos_c = text.index("## C — Code defaults")
    assert pos_p < pos_c

    # P sentence is under P section (between P header and C header)
    pos_p_bullet = text.index("**P1:**")
    assert pos_p < pos_p_bullet < pos_c

    # C sentence is under C section (after C header)
    pos_c_bullet = text.index("**C1:**")
    assert pos_c < pos_c_bullet


def test_p_only_fixture_renders_no_c_section(tmp_path):
    """When only P entries exist, the ## C section is omitted."""
    # Arrange
    _write_entry(tmp_path, "p01", "Only a plan entry.")

    # Act
    text, errors = render_digest(tmp_path)

    # Assert
    assert errors == []
    assert "## P — Plan defaults" in text
    assert "## C — Code defaults" not in text


def test_c_only_fixture_renders_no_p_section(tmp_path):
    """When only C entries exist, the ## P section is omitted."""
    # Arrange
    _write_entry(tmp_path, "c01", "Only a code entry.")

    # Act
    text, errors = render_digest(tmp_path)

    # Assert
    assert errors == []
    assert "## C — Code defaults" in text
    assert "## P — Plan defaults" not in text


# ---------------------------------------------------------------------------
# Test 10 — main() --entries-dir / --digest-path overrides target the given paths
# ---------------------------------------------------------------------------
def test_cli_overrides_check_specified_paths_in_sync(tmp_path):
    """main(['--check', '--entries-dir', D, '--digest-path', F]) returns 0 when D/F are in sync."""
    # Arrange — an entries subdir + a digest written from it (in sync)
    entries_dir = tmp_path / "entries"
    entries_dir.mkdir()
    _write_entry(entries_dir, "p01", "Override path in-sync sentence.")
    digest_path = tmp_path / "digest.md"
    assert write(entries_dir, digest_path) == EXIT_OK

    # Act — check via the CLI overrides (NOT the __file__-relative defaults)
    rc = main(["--check", "--entries-dir", str(entries_dir), "--digest-path", str(digest_path)])

    # Assert
    assert rc == EXIT_OK


def test_cli_overrides_check_specified_paths_on_drift(tmp_path):
    """main(['--check', ...overrides]) returns 3 when the override entries drift from the override digest."""
    # Arrange — write an in-sync digest, then mutate the entry so it drifts
    entries_dir = tmp_path / "entries"
    entries_dir.mkdir()
    _write_entry(entries_dir, "p01", "Original override sentence.")
    digest_path = tmp_path / "digest.md"
    write(entries_dir, digest_path)
    _write_entry(entries_dir, "p01", "MUTATED override sentence causing drift.")

    # Act
    rc = main(["--check", "--entries-dir", str(entries_dir), "--digest-path", str(digest_path)])

    # Assert
    assert rc == EXIT_DIGEST_PROBLEM


def test_cli_overrides_equals_form(tmp_path):
    """The --entries-dir=DIR / --digest-path=FILE equals form is honored too."""
    # Arrange
    entries_dir = tmp_path / "entries"
    entries_dir.mkdir()
    _write_entry(entries_dir, "c01", "Equals-form override sentence.")
    digest_path = tmp_path / "digest.md"
    assert write(entries_dir, digest_path) == EXIT_OK

    # Act
    rc = main(["--check", f"--entries-dir={entries_dir}", f"--digest-path={digest_path}"])

    # Assert
    assert rc == EXIT_OK


# ---------------------------------------------------------------------------
# Test 11 — review face: legacy TABLE-CELL check extraction, including an
# embedded/escaped pipe and backticks (F2, format 1).
# ---------------------------------------------------------------------------
def test_review_face_extracts_table_cell_check_with_escaped_pipe(tmp_path):
    """review face extracts the 3rd table column, unescaping an embedded '\\|' back to a literal '|'."""
    # Arrange
    content = (
        "# C16\n\n"
        "| ID | Pattern | Check before dispatch |\n"
        "|----|---------|----------------------|\n"
        "| C16 | Some pattern | Ask: does X \\| Y \\| Z apply? Verify before dispatch. |\n\n"
        "**Design default:** Some design sentence.\n"
    )
    (tmp_path / "c16-slug.md").write_text(content, encoding="utf-8")

    # Act
    text, errors = render_digest(tmp_path, face=FACE_REVIEW)

    # Assert
    assert errors == []
    assert "### C16" in text
    assert "Ask: does X | Y | Z apply? Verify before dispatch." in text


def test_review_face_table_cell_backticks_preserved(tmp_path):
    """A table-cell check face containing inline-code backticks is extracted verbatim."""
    # Arrange
    content = (
        "# C2\n\n"
        "| ID | Pattern | Check before dispatch |\n"
        "|----|---------|----------------------|\n"
        "| C2 | `@tags: foo` Some pattern text | Confirm `removeOnFail: true` is set. |\n\n"
        "**Design default:** Some design sentence.\n"
    )
    (tmp_path / "c02-slug.md").write_text(content, encoding="utf-8")

    # Act
    text, errors = render_digest(tmp_path, face=FACE_REVIEW)

    # Assert
    assert errors == []
    assert "Confirm `removeOnFail: true` is set." in text


# ---------------------------------------------------------------------------
# Test 12 — review face: standalone MULTI-LINE labeled-section check
# extraction, including a numbered list (F2, format 2).
# ---------------------------------------------------------------------------
def test_review_face_extracts_multiline_labeled_check_with_numbered_list(tmp_path):
    """review face extracts a standalone '**Check before dispatch:**' section, preserving a
    multi-line numbered list, and stops at the NEXT bold '**Label:**' line."""
    # Arrange
    content = (
        "# C24\n\n"
        "`@tags: concurrency-lock; reasoning-shape; scope:diff`\n\n"
        "**Pattern:** A poll-based producer enqueues jobs with a stable dedup key.\n\n"
        "**Check before dispatch:**\n"
        "1. Confirm removeOnFail: true so a failed job frees the key.\n"
        "2. Confirm the scheduler bounds retained job output.\n\n"
        "**Design default:** Make failure free the key and bound scheduler retention.\n"
    )
    (tmp_path / "20260701-133000-0f84-slug.md").write_text(content, encoding="utf-8")

    # Act
    text, errors = render_digest(tmp_path, face=FACE_REVIEW)

    # Assert — both numbered items present; the Design default body is NOT bled into the check
    assert errors == []
    assert "### C24" in text
    assert "1. Confirm removeOnFail: true so a failed job frees the key." in text
    assert "2. Confirm the scheduler bounds retained job output." in text
    assert "Make failure free the key" not in text


# ---------------------------------------------------------------------------
# Test 13 — review face: an entry with NO check face at all is a GAP error.
# ---------------------------------------------------------------------------
def test_review_face_missing_check_face_is_gap_error(tmp_path):
    """review face: an entry with neither a table-cell nor a labeled check face is a GAP error."""
    # Arrange — a Design-default-only entry, no check face anywhere
    content = (
        "# P01\n\n"
        "**Design default:** Some design sentence with no check face anywhere.\n"
    )
    (tmp_path / "p01-slug.md").write_text(content, encoding="utf-8")

    # Act
    text, errors = render_digest(tmp_path, face=FACE_REVIEW)

    # Assert
    assert text == ""
    assert len(errors) == 1
    assert "GAP" in errors[0]


# ---------------------------------------------------------------------------
# Test 14 — review face: an entry with TWO check faces (both formats present
# at once) is a DUPLICATE error.
# ---------------------------------------------------------------------------
def test_review_face_two_check_faces_is_duplicate_error(tmp_path):
    """review face: an entry mixing a table-cell check AND a labeled check section is DUPLICATE."""
    # Arrange
    content = (
        "# C99\n\n"
        "| ID | Pattern | Check before dispatch |\n"
        "|----|---------|----------------------|\n"
        "| C99 | Some pattern | The table-cell check face. |\n\n"
        "**Check before dispatch:**\n"
        "A second, labeled check face that should not coexist with the table cell.\n\n"
        "**Design default:** Some design sentence.\n"
    )
    (tmp_path / "c99-slug.md").write_text(content, encoding="utf-8")

    # Act
    text, errors = render_digest(tmp_path, face=FACE_REVIEW)

    # Assert
    assert text == ""
    assert len(errors) == 1
    assert "DUPLICATE" in errors[0]


# ---------------------------------------------------------------------------
# Test 15 — review face NEGATIVE GATE: a '**Review check:**' label (a
# forbidden third per-entry field, B2 rejected design) is a hard error.
# ---------------------------------------------------------------------------
def test_review_face_review_check_label_is_forbidden(tmp_path):
    """review face: a '**Review check:**' label is FORBIDDEN — the check face IS the review face."""
    # Arrange
    content = (
        "# C50\n\n"
        "| ID | Pattern | Check before dispatch |\n"
        "|----|---------|----------------------|\n"
        "| C50 | Some pattern | The check face. |\n\n"
        "**Review check:** A forbidden third per-entry field.\n\n"
        "**Design default:** Some design sentence.\n"
    )
    (tmp_path / "c50-slug.md").write_text(content, encoding="utf-8")

    # Act
    text, errors = render_digest(tmp_path, face=FACE_REVIEW)

    # Assert
    assert text == ""
    assert len(errors) == 1
    assert "FORBIDDEN" in errors[0]
    assert "Review check" in errors[0]


# ---------------------------------------------------------------------------
# Test 16 — review face: a good set (both formats, exactly one check face
# each) renders with ZERO errors.
# ---------------------------------------------------------------------------
def test_review_face_good_mixed_set_renders_with_zero_errors(tmp_path):
    """A set with BOTH table-cell and labeled-section entries, each with exactly one check
    face, renders with zero errors and both entries present."""
    # Arrange
    table_entry = (
        "# C16\n\n"
        "| ID | Pattern | Check before dispatch |\n"
        "|----|---------|----------------------|\n"
        "| C16 | Some pattern | Table-cell check for C16. |\n\n"
        "**Design default:** Design sentence for C16.\n"
    )
    (tmp_path / "c16-slug.md").write_text(table_entry, encoding="utf-8")

    labeled_entry = (
        "# C24\n\n"
        "**Check before dispatch:**\n"
        "1. First check step.\n"
        "2. Second check step.\n\n"
        "**Design default:** Design sentence for C24.\n"
    )
    (tmp_path / "20260701-133000-0f84-slug.md").write_text(labeled_entry, encoding="utf-8")

    # Act
    text, errors = render_digest(tmp_path, face=FACE_REVIEW)

    # Assert
    assert errors == []
    assert "### C16" in text
    assert "### C24" in text
    assert "Table-cell check for C16." in text
    assert "1. First check step." in text


# ---------------------------------------------------------------------------
# Test 17 — design face output is BYTE-IDENTICAL to the committed
# codex-learnings-digest.md, rendered over the REAL entries dir. This is the
# regression guard: the design face MUST stay unchanged by the review-face
# parameterization.
# ---------------------------------------------------------------------------
def test_design_face_output_is_byte_identical_to_committed_digest():
    """render_digest(face='design') over the REAL entries dir equals the committed digest byte-for-byte."""
    # Arrange
    real_entries_dir = _mod.ENTRIES_DIR
    real_digest_path = _mod.DESIGN_DIGEST_PATH

    # Act
    text, errors = render_digest(real_entries_dir, face=FACE_DESIGN)

    # Assert
    assert errors == []
    committed = real_digest_path.read_text(encoding="utf-8")
    assert text == committed


# ---------------------------------------------------------------------------
# Test 18 — review face: exactly one check face per entry holds across the
# REAL entries dir (every live entry succeeds with zero GAP/DUPLICATE errors).
# ---------------------------------------------------------------------------
def test_review_face_real_entries_dir_has_exactly_one_check_face_each():
    """render_digest(face='review') over the REAL entries dir succeeds with zero errors."""
    # Arrange
    real_entries_dir = _mod.ENTRIES_DIR

    # Act
    text, errors = render_digest(real_entries_dir, face=FACE_REVIEW)

    # Assert
    assert errors == [], errors
    assert text != ""


# ---------------------------------------------------------------------------
# Test 19 — CLI: --face review --check, in sync vs. drifted.
# ---------------------------------------------------------------------------
def test_cli_face_review_check_in_sync(tmp_path):
    """main(['--face','review','--check',...]) returns 0 when the review digest is in sync."""
    # Arrange
    entries_dir = tmp_path / "entries"
    entries_dir.mkdir()
    content = (
        "# C1\n\n"
        "| ID | Pattern | Check before dispatch |\n"
        "|----|---------|----------------------|\n"
        "| C1 | Pattern text | Check text for C1. |\n\n"
        "**Design default:** Design sentence for C1.\n"
    )
    (entries_dir / "c1-slug.md").write_text(content, encoding="utf-8")
    digest_path = tmp_path / "review-digest.md"
    assert write(entries_dir, digest_path, face=FACE_REVIEW) == EXIT_OK

    # Act
    rc = main([
        "--face", "review", "--check",
        "--entries-dir", str(entries_dir), "--digest-path", str(digest_path),
    ])

    # Assert
    assert rc == EXIT_OK


def test_cli_face_review_check_on_drift(tmp_path):
    """main(['--face','review','--check',...]) returns 3 when the review digest drifts from entries."""
    # Arrange
    entries_dir = tmp_path / "entries"
    entries_dir.mkdir()
    content = (
        "# C1\n\n"
        "| ID | Pattern | Check before dispatch |\n"
        "|----|---------|----------------------|\n"
        "| C1 | Pattern text | Original check text. |\n\n"
        "**Design default:** Design sentence.\n"
    )
    (entries_dir / "c1-slug.md").write_text(content, encoding="utf-8")
    digest_path = tmp_path / "review-digest.md"
    write(entries_dir, digest_path, face=FACE_REVIEW)

    mutated = content.replace("Original check text.", "MUTATED check text.")
    (entries_dir / "c1-slug.md").write_text(mutated, encoding="utf-8")

    # Act
    rc = main([
        "--face", "review", "--check",
        "--entries-dir", str(entries_dir), "--digest-path", str(digest_path),
    ])

    # Assert
    assert rc == EXIT_DIGEST_PROBLEM


def test_cli_invalid_face_returns_digest_problem():
    """An unrecognized --face value returns EXIT_DIGEST_PROBLEM rather than silently defaulting."""
    # Act
    rc = main(["--face", "bogus", "--check"])

    # Assert
    assert rc == EXIT_DIGEST_PROBLEM
