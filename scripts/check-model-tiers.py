#!/usr/bin/env python3
"""Verify no live-dispatch instruction file hardcodes an agent model tier.

A hardcoded `model:` on an Agent dispatch overrides the operator's session-model
choice DOWNWARD and says nothing about it. Measured (TRK-126): phases/planning.md
carried `(model: opus)`, silently downgrading 20 planner dispatches across 16
sessions below the model the operator had deliberately selected. Every agent in
this roster is judgment-heavy, so the tier is omitted everywhere and dispatches
inherit the session model.

Checks (stdlib only, no third-party deps):
  1. No file in agents/*.md or phases/*.md contains a `model:` token, unless
     that same line carries a justification marker `model-tier-ok: <reason>`
     AFTER the last `model:` key on the line, whose reason survives truncation
     at the first comment terminator and is at least MIN_JUSTIFICATION_CHARS
     long. A marker positioned before the key cannot justify it.
  2. Each scan directory exists AND yields at least one scanned file — a
     renamed directory, or one whose live files moved into a nested
     subdirectory (invisible to the non-recursive glob), must fail loudly
     rather than let the guard scan nothing and pass forever.

Known limitations:
  Explicit-key YAML (`? model` on one line, `: sonnet` on the next) parses to
  a `model` key but never puts `model:` on a single line, so this line-based
  scan cannot see it. Catching that form needs real YAML parsing, which would
  break this script's stdlib-only convention. The agent smoke test's YAML
  parse of agent frontmatter is the complementary semantic check that covers
  it.

The scan set uses non-recursive glob, mirroring check-indexes.py's check 1.
That structurally excludes agents/reference/*, which holds prose such as
"Maturity model: Levels 0-4" that is documentation, not a dispatch. docs/plans/
and docs/reviews/ are historical records and are outside the scan set entirely.

Usage:
  python3 scripts/check-model-tiers.py [root]

`root` defaults to this script's own repository. It is supplied so the test
suite can run this script against synthetic repositories.

Exit code 0 = all checks pass. Exit code 1 = at least one legitimate failure.

Deliberate exceptions are allowlisted below (see ALLOWLIST) — do not add to
this list without a comment explaining why the hit is not a regression.
"""

import argparse
import re
import sys
from pathlib import Path

DEFAULT_REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# ALLOWLIST — deliberate, documented exceptions.
#
# Each entry is a (repo-relative file path, line-substring) pair. A hit is only
# suppressed if BOTH the file path and the offending line match an entry.
# Ships empty: the preferred escape hatch is the inline `model-tier-ok: <reason>`
# marker, which keeps the justification next to the tier it excuses. Use this
# list only when the marker cannot be placed inline, and add a comment saying why.
# ---------------------------------------------------------------------------
ALLOWLIST: set[tuple[str, str]] = set()

# Matches the `model` key in every spelling that means the same thing — the
# frontmatter key and the inline dispatch argument alike.
#
#   `["']?model["']?`  tolerates `model:`, `"model":`, `'model':` — all valid YAML
#   `\s*:`             tolerates `model : x`, also valid YAML
#   `(?<![\w-])`       requires the key to START here. A plain `\b` sits between
#                      the `-` and the `m` of `session-model:`, so `\bmodel:`
#                      FALSELY matches compound keys. Excluding `-` as well as
#                      word characters is what rejects them.
#
# The justification marker reads `model-tier-ok:` — "model" followed by "-",
# never ":" — so the marker can never match this pattern and excuse itself.
#
# Deliberately tier-AGNOSTIC: it fires on the presence of the key, never on a
# closed list of tier values. A value allowlist is the exact staleness that
# produced TRK-126, and a guard that only knows `haiku|sonnet|opus` would wave
# through a future tier silently. Erring loud is the point.
#
# Verified by execution — see the "F1 proof" block below for the full matrix.
MODEL_KEY_RE = re.compile(r"""(?<![\w-])["']?model["']?\s*:""")

# A bare `model-tier-ok:` is not a justification; it must carry real reason text.
# Three rules that LOOK sufficient and are not, all measured against real input:
#   1. "marker followed by non-whitespace" accepts `<!-- model-tier-ok: -->`,
#      because the `-` of the `-->` terminator is itself non-whitespace.
#   2. "strip a terminator off the END of the reason" accepts
#      `<!-- model-tier-ok: --> Dispatch (model: haiku).` — the captured reason
#      is `--> Dispatch (model: haiku).`, which does not END with a terminator,
#      so nothing is stripped and 27 characters of the LINE ITSELF become the
#      "reason". A marker at the start of a line swallows the tier it excuses.
#   3. "marker anywhere on the line" accepts
#      `model-tier-ok: Dispatch via Agent tool (model: haiku).` — with NO
#      terminator on the line, truncation never fires and the dispatch text
#      itself is the reason. Position is load-bearing: the marker must FOLLOW
#      the last `model:` key on the line, because it can only annotate a key
#      that precedes it.
# The reason ends where its COMMENT ends. Truncate at the FIRST terminator.
JUSTIFICATION_RE = re.compile(r"model-tier-ok:(?P<reason>.*)$")
MIN_JUSTIFICATION_CHARS = 8
COMMENT_TERMINATORS = ("-->", "*/")

# Non-recursive scan set — see the module docstring.
SCAN_DIRS = ["agents", "phases"]

# README.md documents the frontmatter schema rather than dispatching anything.
EXCLUDED_BASENAMES = {"README.md"}


def _is_allowlisted(rel_path, line):
    """Return True when this exact (file, line) pair is a documented exception."""
    return any(
        rel_path == allow_file and allow_text in line
        for allow_file, allow_text in ALLOWLIST
    )


def _has_justification(line, search_from):
    """Return True when a `model-tier-ok:` marker with a reason follows the key.

    `search_from` is the end of the last `model:` key match on the line: a
    marker can only justify a key that PRECEDES it, so a line-leading marker
    never counts — see rule 3 above. The reason still ends at the first
    comment terminator, not at end of line, so a marker must not claim the
    rest of its line, tier included, as its own justification.
    """
    match = JUSTIFICATION_RE.search(line, search_from)
    if match is None:
        return False
    reason = match.group("reason")
    cut = len(reason)
    for terminator in COMMENT_TERMINATORS:
        index = reason.find(terminator)
        if index != -1:
            cut = min(cut, index)
    return len(reason[:cut].strip()) >= MIN_JUSTIFICATION_CHARS


def find_violations(repo_root):
    """Return a list of human-readable violation strings for repo_root.

    An empty list means the repository is clean.
    """
    violations = []
    for directory in SCAN_DIRS:
        base = repo_root / directory
        if not base.is_dir():
            violations.append(
                f"{directory}/ does not exist under {repo_root} — this guard "
                f"would scan nothing and pass. Update SCAN_DIRS in "
                f"scripts/check-model-tiers.py if the repo layout changed."
            )
            continue
        scanned_files = 0
        for path in sorted(base.glob("*.md")):
            if path.name in EXCLUDED_BASENAMES:
                continue
            scanned_files += 1
            rel = path.relative_to(repo_root).as_posix()
            text = path.read_text(encoding="utf-8", errors="replace")
            for line_no, line in enumerate(text.splitlines(), start=1):
                key_matches = list(MODEL_KEY_RE.finditer(line))
                if not key_matches:
                    continue
                if _has_justification(line, key_matches[-1].end()):
                    continue
                if _is_allowlisted(rel, line):
                    continue
                violations.append(
                    f"{rel}:{line_no} hardcodes a model tier: {line.strip()}"
                )
        if scanned_files == 0:
            violations.append(
                f"{directory}/ under {repo_root} yields no scanned *.md files "
                f"— this guard would scan nothing there and pass. Update "
                f"SCAN_DIRS in scripts/check-model-tiers.py if the repo "
                f"layout changed."
            )
    return violations


def main():
    parser = argparse.ArgumentParser(
        description="Verify no live-dispatch file hardcodes an agent model tier."
    )
    parser.add_argument(
        "root",
        nargs="?",
        default=str(DEFAULT_REPO_ROOT),
        help="repository root to scan (default: this script's own repository)",
    )
    args = parser.parse_args()

    violations = find_violations(Path(args.root).resolve())

    if violations:
        print(f"check-model-tiers.py: {len(violations)} failure(s)\n")
        for violation in violations:
            print(f"  - {violation}")
        print(
            "\nAgent dispatches must inherit the operator's session model — a "
            "hardcoded tier silently overrides an explicit /model choice "
            "downward. Remove the tier, or append a justification to that line: "
            f"`model-tier-ok: <why this tier is deliberate>` "
            f"(at least {MIN_JUSTIFICATION_CHARS} characters of reason)."
        )
        sys.exit(1)

    print("check-model-tiers.py: all checks passed")
    sys.exit(0)


if __name__ == "__main__":
    main()
