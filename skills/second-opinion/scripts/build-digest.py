"""
build-digest.py — Deterministic digest generator for codex-learnings.d entries.

Reads every *.md in codex-learnings.d/ (excluding _header.md) and renders a
sorted digest. Two FACES share the same collection/sort/write/check skeleton
(parameterized, not duplicated — see ``--face`` below):

  design (default) — extracts the single ``**Design default:**`` sentence
    from each entry, renders to ``codex-learnings-digest.md``. Author-facing:
    "what to do."
  review — extracts each entry's single CHECK FACE (either a legacy markdown
    table's 3rd "Check before dispatch" column, or a standalone
    ``**Check before dispatch:**`` labeled multi-line section), renders to
    ``codex-learnings-review-digest.md``. Reviewer-facing: "what to verify."

The review face additionally enforces a NEGATIVE gate: an entry containing a
``**Review check:**`` label (a third per-entry field) is a hard error — B2, an
explicitly rejected design. The check face IS the review face; there is no
separate reviewer-only field to keep in sync.

Canonical ID source (the entry HEADING, NOT the filename):
  Each entry's P/C group + number is derived from its FIRST H1 heading line
  (``# <P|C><digits>``, e.g. ``# C1`` or ``# P33``), NOT from the filename.
  New entries are dropped into the folder with a TIMESTAMP filename
  (``<YYYYMMDD-HHMMSS>-<rand4>-<slug>.md``) for concurrency safety, so the
  filename has no P/C prefix to parse. The filename is used ONLY to glob
  ``*.md`` and to exclude ``_header.md``; the ``# <P|C><n>`` heading is the
  canonical ID used for grouping/ordering.

Sort order (NUMERIC-AWARE — deliberate choice documented here):
  Entries are grouped by prefix letter (P first, then C).  Within each group
  the sort key is the INTEGER value of the numeric suffix, NOT the raw string.
  This means c2 < c10 (2 < 10), and the zero-padded real entries c01 < c02 <
  c10 also sort correctly (1 < 2 < 10).  Lexicographic string sort would
  place c10 before c2 ("10" < "2" as strings), which is wrong.  Numeric-aware
  sort is the only correct choice when IDs can have arbitrary widths.

CLI:
  build-digest.py                    → write the design digest (DESIGN_DIGEST_PATH)
  build-digest.py --check            → compare in-memory design render to
                                        DESIGN_DIGEST_PATH, diff on stderr
  build-digest.py --face review      → write the review digest (REVIEW_DIGEST_PATH)
  build-digest.py --face review --check → compare in-memory review render to
                                        REVIEW_DIGEST_PATH, diff on stderr
  build-digest.py --help             → brief usage

  --face design|review selects the face (default design). The two faces share
  the same collect/render/write/check skeleton — only the extractor, the
  default output path, and the rendered header/marker differ per face.

  --entries-dir DIR and --digest-path FILE override the __file__-relative
  defaults for both write and --check (a thin pass-through to render/check).
  This lets a caller (e.g. the digest-sync commit gate) point the check at a
  materialized index tree instead of the working tree.

Exit codes (deliberate scheme — the digest gate distinguishes them):
  0  EXIT_OK            — success (write succeeded, or --check found in sync).
  3  EXIT_DIGEST_PROBLEM — a cleanly-determined digest problem: drift
                          (committed != rendered), a missing digest, or entry
                          errors (gap / duplicate / malformed-or-missing heading).
  1  (implicit)         — Python's DEFAULT uncaught-exception exit. NOT used
                          deliberately here: a genuine crash (syntax error,
                          unexpected exception) propagates to 1 so the gate can
                          tell "the script broke" apart from "the digest is
                          stale" and FAIL OPEN on the crash. We deliberately do
                          NOT wrap main() in a broad try/except.
  (2 is reserved by argparse/usage convention and is intentionally unused.)
"""

import difflib
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path constants — resolved relative to THIS FILE so a hook can invoke the
# script from any cwd without path confusion.
# ---------------------------------------------------------------------------
ENTRIES_DIR = Path(__file__).resolve().parent.parent / "codex-learnings.d"
DESIGN_DIGEST_PATH = Path(__file__).resolve().parent.parent / "codex-learnings-digest.md"
REVIEW_DIGEST_PATH = Path(__file__).resolve().parent.parent / "codex-learnings-review-digest.md"
# Back-compat alias — the design face's path, unchanged name/value from before
# the review face existed. Existing callers referencing DIGEST_PATH keep working.
DIGEST_PATH = DESIGN_DIGEST_PATH

FACE_DESIGN = "design"
FACE_REVIEW = "review"
_VALID_FACES = (FACE_DESIGN, FACE_REVIEW)

# ---------------------------------------------------------------------------
# Exit codes — see module docstring for the full scheme and rationale.
# EXIT_OK (0)             : success / in sync.
# EXIT_DIGEST_PROBLEM (3) : cleanly-determined digest problem (drift, missing,
#                           or entry errors: gap / duplicate / malformed-or-
#                           missing heading). DISTINCT from Python's implicit 1
#                           on an uncaught crash, which the gate fails OPEN on.
# ---------------------------------------------------------------------------
EXIT_OK = 0
EXIT_DIGEST_PROBLEM = 3

# ---------------------------------------------------------------------------
# Regex for extracting the Design default sentence (design face).
# ---------------------------------------------------------------------------
_DESIGN_DEFAULT_RE = re.compile(
    r'^\*\*Design default:\*\*[ \t]+(.+?)[ \t]*$',
    re.MULTILINE,
)

# ---------------------------------------------------------------------------
# Regexes for extracting the check face (review face). Two source formats
# coexist in codex-learnings.d/ (see module docstring):
#   1. Legacy table cell — ``| ID | Pattern | Check before dispatch |`` header
#      followed by a separator row, then the entry's own single data row whose
#      3rd column IS the check face.
#   2. Multi-line labeled section — a standalone ``**Check before dispatch:**``
#      label line, whose body runs until the NEXT bold ``**Label:**`` line (or
#      EOF).
# ---------------------------------------------------------------------------
_TABLE_HEADER_RE = re.compile(
    r'^\|\s*ID\s*\|\s*Pattern\s*\|\s*Check before dispatch\s*\|\s*$'
)
_TABLE_SEP_RE = re.compile(r'^\|[\s:-]+\|[\s:-]+\|[\s:-]+\|\s*$')
_CHECK_LABEL_RE = re.compile(
    r'^\*\*Check before dispatch:\*\*[ \t]*(.*)$',
    re.MULTILINE,
)
_BOLD_LABEL_RE = re.compile(r'^\*\*[^*\n]+:\*\*', re.MULTILINE)
_REVIEW_CHECK_LABEL_RE = re.compile(r'^\*\*Review check:\*\*', re.MULTILINE)


def _split_table_row(line: str) -> list[str]:
    """Split a markdown table row on ``|`` delimiters, char-by-char.

    A ``|`` is NOT a cell delimiter when it is either:
      * backslash-escaped (``\\|``) — unescaped back to a literal ``|`` in
        the returned cell text, or
      * inside an (unterminated) inline-code backtick span — a code span's
        contents (e.g. a Rust ``|p| p.is_empty() || ...`` closure, or a shell
        ``a|b`` alternation) are literal code, not table syntax, even when
        not individually pipe-escaped. Real entries rely on this (see C17).

    Strips whitespace from each cell and drops the empty leading/trailing
    cells produced by the row's own leading/trailing ``|``.
    """
    cells: list[str] = []
    current: list[str] = []
    in_code = False
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if ch == '\\' and i + 1 < n and line[i + 1] == '|':
            current.append('|')
            i += 2
            continue
        if ch == '`':
            in_code = not in_code
            current.append(ch)
            i += 1
            continue
        if ch == '|' and not in_code:
            cells.append(''.join(current))
            current = []
            i += 1
            continue
        current.append(ch)
        i += 1
    cells.append(''.join(current))

    cells = [c.strip() for c in cells]
    if cells and cells[0] == "":
        cells = cells[1:]
    if cells and cells[-1] == "":
        cells = cells[:-1]
    return cells


def _extract_check_faces(text: str) -> list[str]:
    """Return every check-face occurrence found in ``text`` (both formats).

    Collecting ALL occurrences (rather than assuming one format) is what lets
    the caller apply a single "exactly one" invariant regardless of which
    format — or an accidental mix of both — an entry uses.
    """
    faces: list[str] = []

    # Format 1: legacy table cell.
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if _TABLE_HEADER_RE.match(lines[i]):
            j = i + 1
            if j < len(lines) and _TABLE_SEP_RE.match(lines[j]):
                j += 1
            while j < len(lines) and lines[j].strip().startswith('|'):
                cells = _split_table_row(lines[j])
                if len(cells) >= 3 and cells[2].strip():
                    faces.append(cells[2].strip())
                j += 1
            i = j
            continue
        i += 1

    # Format 2: multi-line labeled section.
    for m in _CHECK_LABEL_RE.finditer(text):
        inline = m.group(1).strip()
        start = m.end()
        next_label = _BOLD_LABEL_RE.search(text, start)
        end = next_label.start() if next_label else len(text)
        body = text[start:end].strip('\n')
        parts = [p for p in (inline, body) if p]
        combined = "\n".join(parts).strip()
        if combined:
            faces.append(combined)

    return faces


# ---------------------------------------------------------------------------
# Regex for parsing the canonical entry ID from the first H1 heading line.
# Every entry begins with ``# <P|C><digits>`` (e.g. ``# C1``, ``# P33``); that
# heading — NOT the (timestamp) filename — is the canonical ID. Case-insensitive,
# tolerant of surrounding whitespace on the heading line.
# ---------------------------------------------------------------------------
_HEADING_RE = re.compile(r'^[ \t]*#[ \t]+([PpCc])(\d+)[ \t]*$')


def _parse_heading(text: str) -> tuple[str, int]:
    """Return (group_letter_upper, numeric_id) from the entry's first H1 heading.

    Scans for the FIRST line matching ``# <P|C><digits>`` (case-insensitive,
    surrounding whitespace allowed). Raises ValueError if no such heading exists.
    """
    for line in text.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            group = 'P' if m.group(1).upper() == 'P' else 'C'
            return group, int(m.group(2))
    raise ValueError("no valid '# <P|C><digits>' heading found")


def _display_id(group: str, num: int) -> str:
    """Return display ID like 'P1', 'C10'."""
    return f"{group}{num}"


def _collect_entries(
    entries_dir: Path, face: str = FACE_DESIGN
) -> tuple[list[tuple[str, int, str]], list[str]]:
    """
    Scan entries_dir for *.md files (excluding _header.md).

    Returns:
      (entries, errors)
      entries — list of (group, num, body) tuples, unsorted. ``body`` is the
                Design default sentence (design face) or the check face
                (review face).
      errors  — list of human-readable error strings (gaps, duplicates,
                malformed/missing headings, and — review face only — a
                forbidden ``**Review check:**`` label)

    The filename is used ONLY to glob *.md and to exclude _header.md; the
    canonical P/C id comes from each entry's first ``# <P|C><digits>`` heading.
    """
    entries: list[tuple[str, int, str]] = []
    errors: list[str] = []
    # Track which file(s) declared each canonical (group, num) ID. With
    # timestamp filenames two distinct files can both be headed ``# C10``; that
    # is ambiguous (two contradictory ``**C10:**`` bullets) and is a hard error.
    seen_ids: dict[tuple[str, int], list[str]] = {}

    if face == FACE_REVIEW:
        label = "check face"
    else:
        label = "'**Design default:**' line"

    md_files = sorted(entries_dir.glob("*.md"))
    for path in md_files:
        if path.name == "_header.md":
            continue

        text = path.read_text(encoding="utf-8")
        try:
            group, num = _parse_heading(text)
        except ValueError:
            errors.append(
                f"{path.name}: MALFORMED — no valid '# <P|C><digits>' heading found"
            )
            continue

        seen_ids.setdefault((group, num), []).append(path.name)

        display = _display_id(group, num)

        if face == FACE_REVIEW:
            # Negative gate (B2, rejected design): a third per-entry
            # "review one-liner" field is banned. The check face IS the
            # review face — fix the check cell, do not add a sibling label.
            if _REVIEW_CHECK_LABEL_RE.search(text):
                errors.append(
                    f"{display} ({path.name}): FORBIDDEN — '**Review check:**' "
                    "label found (B2 rejected design: no third per-entry "
                    "field; the check face IS the review face)"
                )
                continue
            matches = _extract_check_faces(text)
        else:
            matches = _DESIGN_DEFAULT_RE.findall(text)

        if len(matches) == 0:
            errors.append(f"{display} ({path.name}): GAP — no {label} found")
        elif len(matches) >= 2:
            errors.append(
                f"{display} ({path.name}): DUPLICATE — found {len(matches)} {label}s"
            )
        else:
            body = matches[0].rstrip()
            entries.append((group, num, body))

    # A canonical ID claimed by more than one file is a deterministic error:
    # the digest cannot pick which entry's sentence to render. Reported with the
    # offending filenames so the author can resolve the collision.
    for (group, num), files in seen_ids.items():
        if len(files) >= 2:
            display = _display_id(group, num)
            joined = " and ".join(sorted(files))
            errors.append(f"DUPLICATE ID {display} — appears in {joined}")

    return entries, errors


def render_digest(entries_dir: Path, face: str = FACE_DESIGN) -> tuple[str, list[str]]:
    """
    Render the digest string for the given entries_dir and face.

    Returns (digest_text, errors).  If errors is non-empty, digest_text is
    empty and the caller MUST NOT write the digest.

    ``face='design'`` (default) is BYTE-IDENTICAL to the original
    (pre-review-face) behavior. ``face='review'`` renders the check-face
    digest instead — same collect/sort/normalize skeleton, different
    extractor + header + per-entry rendering (a check face is often
    multi-line, so it renders as a heading + body rather than a one-line
    bullet).
    """
    entries, errors = _collect_entries(entries_dir, face)
    if errors:
        return "", errors

    # Group and sort (numeric-aware — see module docstring).
    p_entries = sorted(
        [(num, body) for (g, num, body) in entries if g == 'P'],
        key=lambda t: t[0],
    )
    c_entries = sorted(
        [(num, body) for (g, num, body) in entries if g == 'C'],
        key=lambda t: t[0],
    )

    lines: list[str] = []

    if face == FACE_REVIEW:
        lines.append("<!-- generated by build-digest.py --face review — do not edit by hand -->")
        lines.append("")
        lines.append("# Codex Review Digest")
        lines.append("")
        lines.append("Check-face of recurring Codex-caught defects. Cite any entry that applies.")

        if p_entries:
            lines.append("")
            lines.append("## P — Plan checks")
            for num, body in p_entries:
                lines.append("")
                lines.append(f"### {_display_id('P', num)}")
                lines.extend(body.splitlines())

        if c_entries:
            lines.append("")
            lines.append("## C — Code checks")
            for num, body in c_entries:
                lines.append("")
                lines.append(f"### {_display_id('C', num)}")
                lines.extend(body.splitlines())
    else:
        # Header comment — EXACT marker string (em-dash).
        lines.append("<!-- generated by build-digest.py — do not edit by hand -->")
        lines.append("")
        lines.append("# Codex Design Defaults")
        lines.append("")
        lines.append(
            "Author-facing design defaults distilled from codex-learnings.d entries."
            " One line per entry."
        )

        if p_entries:
            lines.append("")
            lines.append("## P — Plan defaults")
            for num, body in p_entries:
                lines.append(f"- **{_display_id('P', num)}:** {body}")

        if c_entries:
            lines.append("")
            lines.append("## C — Code defaults")
            for num, body in c_entries:
                lines.append(f"- **{_display_id('C', num)}:** {body}")

    # Strip trailing spaces from every line (none expected, but enforce rule).
    clean_lines = [ln.rstrip() for ln in lines]

    # Exactly one trailing newline.
    text = "\n".join(clean_lines) + "\n"

    # Enforce LF-only (in case platform inserted CR).
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    return text, []


def write(entries_dir: Path, digest_path: Path, face: str = FACE_DESIGN) -> int:
    """
    Render and write the digest.

    Returns EXIT_OK (0) on success, EXIT_DIGEST_PROBLEM (3) on entry errors
    (gap / duplicate / bad stem). On error, prints to stderr and does NOT write
    the file.
    """
    text, errors = render_digest(entries_dir, face)
    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        return EXIT_DIGEST_PROBLEM

    digest_path.write_text(text, encoding="utf-8")
    return EXIT_OK


def check(entries_dir: Path, digest_path: Path, face: str = FACE_DESIGN) -> int:
    """
    Compare in-memory render to the committed digest_path.

    Returns EXIT_OK (0) if identical. Returns EXIT_DIGEST_PROBLEM (3) for a
    cleanly-determined digest problem: entry errors (gap / duplicate / bad
    stem), a missing digest, or drift (committed != rendered). Prints a unified
    diff to stderr when they differ, and entry errors to stderr otherwise.
    NEVER writes the file.

    A genuine crash (uncaught exception) is intentionally NOT mapped here — it
    propagates to Python's implicit exit 1 so callers can distinguish a broken
    script from a stale digest.
    """
    text, errors = render_digest(entries_dir, face)
    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        return EXIT_DIGEST_PROBLEM

    if not digest_path.exists():
        print(f"MISSING: {digest_path}", file=sys.stderr)
        return EXIT_DIGEST_PROBLEM

    committed = digest_path.read_text(encoding="utf-8")
    if text == committed:
        return EXIT_OK

    diff = difflib.unified_diff(
        committed.splitlines(keepends=True),
        text.splitlines(keepends=True),
        fromfile=str(digest_path),
        tofile="<generated>",
    )
    sys.stderr.writelines(diff)
    return EXIT_DIGEST_PROBLEM


def _extract_option(argv: list[str], name: str) -> str | None:
    """Return the value of ``--name VALUE`` or ``--name=VALUE`` in argv, or None.

    Last occurrence wins. Does NOT mutate argv. A trailing ``--name`` with no
    following value yields None (treated as absent → default path is used).
    """
    value: str | None = None
    prefix = name + "="
    i = 0
    while i < len(argv):
        token = argv[i]
        if token == name:
            if i + 1 < len(argv):
                value = argv[i + 1]
            i += 2
            continue
        if token.startswith(prefix):
            value = token[len(prefix):]
        i += 1
    return value


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns an exit code (see module docstring: 0 / 3, plus
    Python's implicit 1 on any uncaught crash — deliberately NOT swallowed)."""
    if argv is None:
        argv = sys.argv[1:]

    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return EXIT_OK

    face_override = _extract_option(argv, "--face")
    face = face_override if face_override in _VALID_FACES else FACE_DESIGN
    if face_override is not None and face_override not in _VALID_FACES:
        print(f"--face must be one of {_VALID_FACES}, got {face_override!r}", file=sys.stderr)
        return EXIT_DIGEST_PROBLEM

    entries_override = _extract_option(argv, "--entries-dir")
    digest_override = _extract_option(argv, "--digest-path")
    default_digest_path = REVIEW_DIGEST_PATH if face == FACE_REVIEW else DESIGN_DIGEST_PATH
    entries_dir = Path(entries_override) if entries_override else ENTRIES_DIR
    digest_path = Path(digest_override) if digest_override else default_digest_path

    if "--check" in argv:
        return check(entries_dir, digest_path, face)

    return write(entries_dir, digest_path, face)


if __name__ == "__main__":
    sys.exit(main())
