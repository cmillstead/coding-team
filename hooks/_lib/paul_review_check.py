"""CLI exit-code checker for the instruction-layer (Path C).

Exit 0 iff a valid Codex PASS artifact is bound to the current plan content.
Exit 1 on any non-OK status. Prints the status + actionable detail so the
caller (apply-phase.md) can show a banner.

Usage: python3 paul_review_check.py --plan <path>
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _lib import paul_review  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Check PAUL plan-review PASS artifact.")
    parser.add_argument("--plan", required=True)
    args = parser.parse_args()

    ok, status, detail = paul_review.validate_review(Path(args.plan))
    if ok:
        print(f"OK: {detail}")
        return 0
    print(f"{status}: {detail}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
