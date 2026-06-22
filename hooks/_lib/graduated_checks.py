"""Registry of graduated Codex-learning checks.

Provides a dispatch mechanism that runs ALL registered checks and aggregates
results — not first-hit. This design ensures that when multiple checks apply
to the same edit, the author sees every advisory or block reason in one pass.

Adding a new graduation:
1. Write a callable matching signature ``(tool_name: str, tool_input: dict) -> CheckResult | None``
2. Append it to GRADUATED_CHECKS.
"""

import re
from dataclasses import dataclass
from typing import Callable, Literal


@dataclass
class CheckResult:
    """Result from a graduated check.

    Attributes:
        reason: Human-readable explanation to surface to the author.
        mode:   "advisory" emits allow+reason; "block" emits block+reason.
    """
    reason: str
    mode: Literal["advisory", "block"]


# ---------------------------------------------------------------------------
# C1 — single-gate path trust boundary (graduated 2026-06-21)
# ---------------------------------------------------------------------------

# Verbatim design default from c01-single-gate-path-trust.md line 7.
_C1_DESIGN_DEFAULT = (
    "When a task spec introduces a path-shaped field, classify it as "
    "identifier / filesystem-path / repo-relative and state the validation "
    "tier for each — never a lone contains('/') check."
)
_C1_REASON = f"Graduated Codex learning C1 — {_C1_DESIGN_DEFAULT}"

# Signal 1: path-shaped field / identifier name.
#
# Case-SENSITIVE (no re.IGNORECASE) so that path tokens match only as whole
# words or camelCase/snake components — not as mid-word substrings.
# re.IGNORECASE would fire on profile, report, repository, directory, redirect,
# destination, destroy, prefixed, rootkit, turning the reminder into noise.
#
# Lowercase branch uses (?<![A-Za-z]) instead of \b because _ is a word char:
#   \b fails to anchor a token that follows _ (e.g. storage_path — "path" is
#   preceded by _ so \b sees no word-boundary there). (?<![A-Za-z]) excludes
#   only letter predecessors, so _path matches but "profile" (p followed by
#   "rofile") is excluded by (?![a-z]) on the right.
#
# (?![a-z]) on both branches rules out mid-word suffixes (report→"eport",
# directory→"irectory", destination→"estination" are all lowercase continuations).
_FIELD_NAME_RE = re.compile(
    # lowercase whole-word OR snake-case component (path, file_path, storage_path, output_path)
    r"(?<![A-Za-z])(?:path|dir|file|repo|root|prefix|dest|src)(?![a-z])"
    # capitalized camelCase component (filePath, repoPath, storagePath, pathPrefix)
    r"|(?:Path|Dir|File|Repo|Root|Prefix|Dest|Src)(?![a-z])"
)

# Signal 2: path API call tokens. Regex metacharacters (especially the literal
# "(" in "open(" and "Path(") must be escaped — do not paste them raw into
# a regex alternation.
_PATH_CALL_TOKENS = [
    "path.resolve",
    "open(",
    "fs::",
    "include_str!",
    "Path(",
    "join(",
]

# Signal 3: single-gate contains check in either quote style.
_SINGLE_GATE_RE = re.compile(
    r'\.contains\s*\(\s*(?:"/"|\'/\')\s*\)',
)


# Responsibility: C1 — classify path-shaped FIELDS by trust tier; distinct from C17's
# path-equality comparison (see check_path_safety).
def check_c1_path_trust(tool_name: str, tool_input: dict) -> CheckResult | None:
    """Advisory when content contains path-trust C1 signals.

    Fires on ANY of:
    1. A path-shaped field / identifier name (repoPath, filePath, storagePath, …)
    2. A path API call (path.resolve, open(, fs::, include_str!, Path(, join()
    3. A lone .contains("/") or .contains('/') check

    Language-agnostic — no file-extension gate. Broad match is intentional
    (advisory only; false-positives are acceptable reminders).

    Content source:
    - Write tool → tool_input["content"]
    - Edit tool  → tool_input["new_string"]
    - Any other tool → returns None (nothing to inspect)
    """
    if tool_name == "Write":
        content = tool_input.get("content", "")
    elif tool_name == "Edit":
        content = tool_input.get("new_string", "")
    else:
        return None

    if not content:
        return None

    # Signal 1: path-shaped field name
    if _FIELD_NAME_RE.search(content):
        return CheckResult(reason=_C1_REASON, mode="advisory")

    # Signal 2: path call tokens (plain substring checks — avoids regex-escaping
    # issues with literal parentheses and colons)
    for token in _PATH_CALL_TOKENS:
        if token in content:
            return CheckResult(reason=_C1_REASON, mode="advisory")

    # Signal 3: single-gate contains check
    if _SINGLE_GATE_RE.search(content):
        return CheckResult(reason=_C1_REASON, mode="advisory")

    return None


# ---------------------------------------------------------------------------
# Registry — ordered list of check callables
# ---------------------------------------------------------------------------

CheckCallable = Callable[[str, dict], "CheckResult | None"]

GRADUATED_CHECKS: list[CheckCallable] = [
    check_c1_path_trust,
]


def dispatch(tool_name: str, tool_input: dict) -> list[CheckResult]:
    """Run every registered check and return ALL non-None results in registry order.

    Design: all-hit, not first-hit. A first-hit API would silently drop the
    2nd+ graduated advisory once more entries are added to GRADUATED_CHECKS.
    Empty list means no check fired.
    """
    results: list[CheckResult] = []
    for check in GRADUATED_CHECKS:
        result = check(tool_name, tool_input)
        if result is not None:
            results.append(result)
    return results
