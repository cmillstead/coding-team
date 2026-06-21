"""
build-digest.py — Deterministic digest generator for codex-learnings.d entries.

Reads every *.md in codex-learnings.d/ (excluding _header.md), extracts the
single ``**Design default:**`` sentence from each, and renders a sorted digest
to codex-learnings-digest.md.

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
  build-digest.py           → write DIGEST_PATH
  build-digest.py --check   → compare in-memory render to DIGEST_PATH, diff on stderr
  build-digest.py --help    → brief usage

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
DIGEST_PATH = Path(__file__).resolve().parent.parent / "codex-learnings-digest.md"

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
# Regex for extracting the Design default sentence.
# ---------------------------------------------------------------------------
_DESIGN_DEFAULT_RE = re.compile(
    r'^\*\*Design default:\*\*[ \t]+(.+?)[ \t]*$',
    re.MULTILINE,
)

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


def _collect_entries(entries_dir: Path) -> tuple[list[tuple[str, int, str]], list[str]]:
    """
    Scan entries_dir for *.md files (excluding _header.md).

    Returns:
      (entries, errors)
      entries — list of (group, num, sentence) tuples, unsorted
      errors  — list of human-readable error strings (gaps, duplicates,
                malformed/missing headings)

    The filename is used ONLY to glob *.md and to exclude _header.md; the
    canonical P/C id comes from each entry's first ``# <P|C><digits>`` heading.
    """
    entries: list[tuple[str, int, str]] = []
    errors: list[str] = []
    # Track which file(s) declared each canonical (group, num) ID. With
    # timestamp filenames two distinct files can both be headed ``# C10``; that
    # is ambiguous (two contradictory ``**C10:**`` bullets) and is a hard error.
    seen_ids: dict[tuple[str, int], list[str]] = {}

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

        matches = _DESIGN_DEFAULT_RE.findall(text)

        display = _display_id(group, num)
        if len(matches) == 0:
            errors.append(f"{display} ({path.name}): GAP — no '**Design default:**' line found")
        elif len(matches) >= 2:
            errors.append(
                f"{display} ({path.name}): DUPLICATE — found {len(matches)} '**Design default:**' lines"
            )
        else:
            sentence = matches[0].rstrip()
            entries.append((group, num, sentence))

    # A canonical ID claimed by more than one file is a deterministic error:
    # the digest cannot pick which entry's sentence to render. Reported with the
    # offending filenames so the author can resolve the collision.
    for (group, num), files in seen_ids.items():
        if len(files) >= 2:
            display = _display_id(group, num)
            joined = " and ".join(sorted(files))
            errors.append(f"DUPLICATE ID {display} — appears in {joined}")

    return entries, errors


def render_digest(entries_dir: Path) -> tuple[str, list[str]]:
    """
    Render the digest string for the given entries_dir.

    Returns (digest_text, errors).  If errors is non-empty, digest_text is
    empty and the caller MUST NOT write the digest.
    """
    entries, errors = _collect_entries(entries_dir)
    if errors:
        return "", errors

    # Group and sort (numeric-aware — see module docstring).
    p_entries = sorted(
        [(num, sentence) for (g, num, sentence) in entries if g == 'P'],
        key=lambda t: t[0],
    )
    c_entries = sorted(
        [(num, sentence) for (g, num, sentence) in entries if g == 'C'],
        key=lambda t: t[0],
    )

    lines: list[str] = []

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
        for num, sentence in p_entries:
            lines.append(f"- **{_display_id('P', num)}:** {sentence}")

    if c_entries:
        lines.append("")
        lines.append("## C — Code defaults")
        for num, sentence in c_entries:
            lines.append(f"- **{_display_id('C', num)}:** {sentence}")

    # Strip trailing spaces from every line (none expected, but enforce rule).
    clean_lines = [ln.rstrip() for ln in lines]

    # Exactly one trailing newline.
    text = "\n".join(clean_lines) + "\n"

    # Enforce LF-only (in case platform inserted CR).
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    return text, []


def write(entries_dir: Path, digest_path: Path) -> int:
    """
    Render and write the digest.

    Returns EXIT_OK (0) on success, EXIT_DIGEST_PROBLEM (3) on entry errors
    (gap / duplicate / bad stem). On error, prints to stderr and does NOT write
    the file.
    """
    text, errors = render_digest(entries_dir)
    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        return EXIT_DIGEST_PROBLEM

    digest_path.write_text(text, encoding="utf-8")
    return EXIT_OK


def check(entries_dir: Path, digest_path: Path) -> int:
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
    text, errors = render_digest(entries_dir)
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

    entries_override = _extract_option(argv, "--entries-dir")
    digest_override = _extract_option(argv, "--digest-path")
    entries_dir = Path(entries_override) if entries_override else ENTRIES_DIR
    digest_path = Path(digest_override) if digest_override else DIGEST_PATH

    if "--check" in argv:
        return check(entries_dir, digest_path)

    return write(entries_dir, digest_path)


if __name__ == "__main__":
    sys.exit(main())
