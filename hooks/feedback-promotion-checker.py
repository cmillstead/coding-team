#!/usr/bin/env python3
"""Feedback-to-constraint promotion checker.

Scans feedback memory files in the coding-team repo and identifies
candidates for promotion from prompt-level enforcement to structural
enforcement (hooks or rules).

Promotion criteria:
1. Describes a mechanically detectable pattern (not behavioral/subjective)
2. Has been violated 2+ times (evidence of prompt-level enforcement failure)
3. Not already enforced by a hook or rule

Usage: python3 hooks/feedback-promotion-checker.py
"""

import json
import re
from pathlib import Path

MEMORY_DIR = Path(__file__).parent.parent / "memory"
HOOKS_DIR = Path(__file__).parent
RULES_DIR = Path.home() / ".claude" / "rules"

# Keywords that suggest mechanical detectability
MECHANICAL_KEYWORDS = [
    "file", "path", "import", "command", "commit", "branch",
    "test", "lint", "error", "warning", "json", "schema",
    "deploy", "migration", "dependency", "hook", "config",
]

# Keywords that suggest behavioral/subjective (not mechanically detectable)
BEHAVIORAL_KEYWORDS = [
    "think", "consider", "prefer", "should", "avoid",
    "approach", "strategy", "design", "architecture",
    "judgment", "decision", "context", "nuance",
]


def load_feedback_files() -> list[dict]:
    """Load all feedback memory files with their content."""
    feedbacks = []
    if not MEMORY_DIR.exists():
        return feedbacks

    for f in sorted(MEMORY_DIR.glob("feedback-*.md")):
        try:
            content = f.read_text()
            feedbacks.append({"path": f, "name": f.stem, "content": content})
        except OSError:
            continue
    return feedbacks


def get_existing_hooks() -> set[str]:
    """Get names of existing hook files."""
    return {f.stem for f in HOOKS_DIR.glob("*.py") if f.name != "__init__.py"}


def get_existing_rules() -> set[str]:
    """Get names of existing rule files."""
    if not RULES_DIR.exists():
        return set()
    return {f.stem for f in RULES_DIR.glob("*.md")}


def score_mechanicality(content: str) -> tuple[int, int]:
    """Score how mechanically detectable a feedback pattern is.

    Returns (mechanical_score, behavioral_score).
    """
    content_lower = content.lower()
    mechanical = sum(1 for kw in MECHANICAL_KEYWORDS if kw in content_lower)
    behavioral = sum(1 for kw in BEHAVIORAL_KEYWORDS if kw in content_lower)
    return mechanical, behavioral


def check_already_enforced(name: str, content: str, hooks: set[str], rules: set[str]) -> str | None:
    """Check if feedback is already enforced structurally. Returns enforcer name or None."""
    # Check if the feedback name maps to a known hook or rule
    name_clean = name.replace("feedback-", "")
    for hook in hooks:
        if name_clean in hook or hook in name_clean:
            return f"hook:{hook}"
    for rule in rules:
        if name_clean in rule or rule in name_clean:
            return f"rule:{rule}"

    # Check content for references to hooks/rules
    if re.search(r'(fixed with|enforced by|promoted to)\s+(hook|rule)', content, re.I):
        return "referenced in content"

    return None


def analyze() -> list[dict]:
    """Analyze feedback files and return promotion candidates."""
    feedbacks = load_feedback_files()
    hooks = get_existing_hooks()
    rules = get_existing_rules()
    candidates = []

    for fb in feedbacks:
        enforcer = check_already_enforced(fb["name"], fb["content"], hooks, rules)
        mechanical, behavioral = score_mechanicality(fb["content"])

        status = "enforced" if enforcer else (
            "candidate" if mechanical > behavioral else "behavioral"
        )

        candidates.append({
            "name": fb["name"],
            "status": status,
            "enforcer": enforcer,
            "mechanical_score": mechanical,
            "behavioral_score": behavioral,
        })

    return candidates


def main():
    candidates = analyze()
    if not candidates:
        print("No feedback files found.")
        return

    promotable = [c for c in candidates if c["status"] == "candidate"]
    enforced = [c for c in candidates if c["status"] == "enforced"]
    behavioral = [c for c in candidates if c["status"] == "behavioral"]

    print(f"Feedback promotion analysis: {len(candidates)} total")
    print(f"  Already enforced: {len(enforced)}")
    print(f"  Promotion candidates: {len(promotable)}")
    print(f"  Behavioral (not mechanically detectable): {len(behavioral)}")
    print()

    if promotable:
        print("=== PROMOTION CANDIDATES ===")
        for c in sorted(promotable, key=lambda x: x["mechanical_score"], reverse=True):
            print(f"  {c['name']} (mechanical:{c['mechanical_score']} behavioral:{c['behavioral_score']})")
        print()

    if enforced:
        print("=== ALREADY ENFORCED ===")
        for c in enforced:
            print(f"  {c['name']} → {c['enforcer']}")
        print()

    if behavioral:
        print("=== BEHAVIORAL (prompt-level OK) ===")
        for c in behavioral:
            print(f"  {c['name']}")

    # Output as JSON for programmatic consumption
    print("\n--- JSON ---")
    print(json.dumps({"candidates": promotable, "enforced": enforced, "behavioral": behavioral}, indent=2))


if __name__ == "__main__":
    main()
