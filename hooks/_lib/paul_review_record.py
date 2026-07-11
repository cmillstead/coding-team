"""CLI recorder: writes the .review.json PASS artifact with a FRESH hash.

NEVER hand-writes the hash — always computes it via paul_review.compute_plan_hash
so recorder and gate cannot drift. Invoked by /second-opinion Mode 1 on a
PAUL-plan PASS.

Usage:
  python3 paul_review_record.py --plan <abs-plan> --reviewer codex \
      --rounds <N> --session <id> --detail "<one line>"

Exit codes: 0 on success, non-zero on any error (missing plan, unwritable dir).
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _lib import paul_review  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Record a PAUL plan-review PASS.")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--reviewer", default="codex")
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--session", default="")
    parser.add_argument("--detail", default="")
    args = parser.parse_args()

    plan = Path(args.plan)
    try:
        plan_hash = paul_review.compute_plan_hash(plan)
    except (OSError, FileNotFoundError) as exc:
        print(f"paul_review_record: cannot read plan {plan}: {exc}", file=sys.stderr)
        return 1

    artifact = {
        "schema_version": 1,
        "plan_path": str(plan),
        "plan_sha256": plan_hash,
        "verdict": "PASS",
        "reviewer": args.reviewer,
        "reviewer_detail": args.detail,
        "rounds": args.rounds,
        "session": args.session,
        "date": date.today().isoformat(),
        "recorded_by": "/second-opinion",
    }
    review_path = paul_review.review_path_for(plan)
    try:
        review_path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"paul_review_record: cannot write {review_path}: {exc}", file=sys.stderr)
        return 1

    print(f"Recorded Codex PASS for {plan.name} -> {review_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
