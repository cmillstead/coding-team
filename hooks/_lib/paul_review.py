"""Shared PAUL plan-review detection primitive.

Single source of truth for:
  - canonical plan-content hashing (compute_plan_hash)
  - the sibling .review.json path (review_path_for)
  - PASS-artifact validation (validate_review)
  - the /paul:apply prompt regex (APPLY_RE)
  - plan-arg path resolution (resolve_plan_arg)

Recorder and gate MUST share compute_plan_hash so a post-PASS content edit
changes the hash -> STALE -> block (KB 6397: write-time origin binding).
CRLF / trailing-newline churn is normalized away so editors do not cause
false STALE (KB 5162: gen-eval separation -> reviewer must be codex).
"""

import hashlib
import json
import re
from pathlib import Path

APPLY_RE = re.compile(r"^\s*/paul:apply\b\s*(\S+)?", re.IGNORECASE)

# Status constants (also used by consumers for messaging).
OK = "OK"
MISSING = "MISSING"
MALFORMED = "MALFORMED"
NOT_PASS = "NOT_PASS"
WRONG_REVIEWER = "WRONG_REVIEWER"
STALE = "STALE"
PLAN_UNREADABLE = "PLAN_UNREADABLE"

_FIX_HINT = (
    "Run `/second-opinion review <plan>` to get a Codex PASS, then re-run "
    "/paul:apply. To bypass (logged, not recommended), include the phrase "
    "`override-plan-review <reason>` in your APPLY prompt."
)


def compute_plan_hash(plan_path: Path) -> str:
    """Return sha256 hexdigest of the canonicalized plan bytes.

    Canonicalization: CRLF->LF, lone CR->LF, strip a single trailing LF.
    No other whitespace changes, no frontmatter parsing, no re-serialization.
    Raises OSError/FileNotFoundError if the plan cannot be read (callers guard).
    """
    raw = Path(plan_path).read_bytes()
    normalized = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    if normalized.endswith(b"\n"):
        normalized = normalized[:-1]
    return hashlib.sha256(normalized).hexdigest()


def review_path_for(plan_path: Path) -> Path:
    """Return the sibling .review.json path for a plan.

    `X-PLAN.md` -> `X-PLAN.review.json`. If the name does not end in `.md`,
    append `.review.json` to the full name (defensive; PAUL plans always end
    in `-PLAN.md`).
    """
    plan_path = Path(plan_path)
    name = plan_path.name
    if name.endswith(".md"):
        review_name = name[: -len(".md")] + ".review.json"
    else:
        review_name = name + ".review.json"
    return plan_path.with_name(review_name)


def validate_review(plan_path: Path) -> tuple[bool, str, str]:
    """Validate the PASS artifact bound to plan_path.

    Returns (ok, status, detail). detail is an actionable instruction
    (golden principle 15: error messages are instructions). Fail-closed:
    any non-OK status returns ok=False. The plan path is the caller's
    invocation arg — NEVER the .review.json plan_path field (prevents redirect).
    """
    plan_path = Path(plan_path)

    # Compute the fresh hash first: if the plan itself is unreadable, we cannot
    # validate anything — fail closed with a distinct status.
    try:
        fresh_hash = compute_plan_hash(plan_path)
    except (OSError, FileNotFoundError):
        return (False, PLAN_UNREADABLE,
                f"Plan file not readable: {plan_path}. Check the path. {_FIX_HINT}")

    review = review_path_for(plan_path)
    try:
        text = review.read_text(encoding="utf-8")
    except (OSError, FileNotFoundError):
        return (False, MISSING,
                f"No Codex plan-review artifact for {plan_path.name}. {_FIX_HINT}")

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return (False, MALFORMED,
                f"Review artifact {review.name} is not valid JSON. "
                f"Delete it and re-run `/second-opinion review <plan>`. {_FIX_HINT}")

    if not isinstance(data, dict):
        return (False, MALFORMED,
                f"Review artifact {review.name} is not a JSON object. {_FIX_HINT}")

    if data.get("verdict") != "PASS":
        return (False, NOT_PASS,
                f"Codex verdict for {plan_path.name} is "
                f"{data.get('verdict')!r}, not PASS. {_FIX_HINT}")

    if data.get("reviewer") != "codex":
        return (False, WRONG_REVIEWER,
                f"Review artifact reviewer is {data.get('reviewer')!r}, not "
                f"'codex'. An out-of-band evaluator (Codex) is required. {_FIX_HINT}")

    if data.get("plan_sha256") != fresh_hash:
        return (False, STALE,
                f"Plan {plan_path.name} was edited after its Codex PASS "
                f"(hash mismatch). Re-run `/second-opinion review <plan>` to "
                f"re-approve the current content. {_FIX_HINT}")

    return (True, OK, "Codex PASS artifact valid for current plan content.")


def resolve_plan_arg(arg: str, cwd: Path) -> Path:
    """Resolve a plan arg (abs or cwd-relative) to an absolute Path.

    Does not check existence; validate_review handles unreadable plans.
    """
    p = Path(arg)
    return p if p.is_absolute() else (Path(cwd) / p)
