"""
Tests for build-digest.py

Uses real temp directories (tmp_path), no mocks. AAA pattern throughout.
"""

import importlib.util
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_entry(entries_dir: Path, stem: str, design_default: str | None = None) -> Path:
    """Write a minimal entry file to entries_dir."""
    lines = [
        f"# {stem.upper()}",
        "",
        "| ID | Pattern | Check before dispatch |",
        "|----|---------|----------------------|",
        f"| {stem} | Some pattern | Some check |",
        "",
    ]
    if design_default is not None:
        lines.append(f"**Design default:** {design_default}")
    content = "\n".join(lines) + "\n"
    path = entries_dir / f"{stem}-some-slug.md"
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
# Test 3b — BAD STEM: filename stem not <p|c><digits> surfaces an error,
# returns EXIT_DIGEST_PROBLEM, and writes no digest.
# ---------------------------------------------------------------------------
def test_bad_stem_is_reported_in_errors(tmp_path):
    """An entry whose stem is not <p|c><digits> (e.g. 'x99-foo') surfaces an error."""
    # Arrange — a real entry body, but a filename stem the parser rejects.
    content = (
        "# X99\n\n"
        "| ID | Pattern | Check |\n"
        "|----|---------|------|\n"
        "| X99 | A | B |\n\n"
        "**Design default:** This entry has a valid body but a bad stem.\n"
    )
    (tmp_path / "x99-foo.md").write_text(content, encoding="utf-8")

    # Act
    text, errors = render_digest(tmp_path)

    # Assert — the bad stem is surfaced and the render is suppressed.
    assert text == ""
    assert len(errors) == 1
    assert "x99-foo" in errors[0]


def test_bad_stem_causes_digest_problem_exit_and_no_digest_written(tmp_path):
    """A bad-stem entry returns EXIT_DIGEST_PROBLEM (3) via write() and writes no digest."""
    # Arrange
    content = (
        "# X99\n\n"
        "| ID | Pattern | Check |\n"
        "|----|---------|------|\n"
        "| X99 | A | B |\n\n"
        "**Design default:** Bad stem, valid body.\n"
    )
    (tmp_path / "x99-foo.md").write_text(content, encoding="utf-8")
    digest_path = tmp_path / "digest.md"

    # Act
    result = write(tmp_path, digest_path)

    # Assert — dedicated digest-problem code (3), and digest NOT written.
    assert result == EXIT_DIGEST_PROBLEM
    assert not digest_path.exists()


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
    """c2 must sort before c10 numerically (2 < 10), not lexicographically ("10" < "2")."""
    # Arrange — write c10 first so filesystem order is "wrong" for lexicographic sort
    _write_entry(tmp_path, "c10", "Sentence for C10.")
    _write_entry(tmp_path, "c2", "Sentence for C2.")

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
# fail (the stem "digest" does not match the <p|c><digits> pattern).
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
