#!/usr/bin/env python3
"""Path B fence: block an Agent dispatch that executes a PAUL plan lacking a
fresh Codex PASS.

PreToolUse hook, active only for tool_name == "Agent". Reads the Agent prompt
(and description), finds referenced .paul/phases/*/*-PLAN.md paths, and — for
references with execution-intent near them — validates the Codex PASS. If any
execution-intent plan reference lacks a valid PASS, emits
{"decision":"block","reason":...} on stdout (exit 0).

THREAT MODEL / BIAS (deliberate refinement): Path B is the PRIMARY structural
fence for the user's real apply path — Path A covers only literal /paul:apply
prompts, and Path C (apply-phase.md) fires only if the workflow is loaded. For
Path B, a FALSE NEGATIVE (missing a real execution dispatch) silently applies a
plan with NO Codex PASS and DEFEATS the fence; a false positive (blocking a pure
review dispatch) costs one override cycle and is recoverable. Therefore Path B
LEANS BLOCK: any genuine exec verb near a real plan-ref → block (fail-closed),
with override as the escape. The ONLY ambiguity we still avoid is "no exec verb
near the ref" (a pure review/discuss dispatch has no exec verb, so it never
fires). We do NOT suppress on review framing, and we suppress a specific exec
verb ONLY when a negation token immediately precedes THAT verb.

Escape hatches:
  PAUL_APPLY_GATE_DISABLE=1                 -> pass.
  prompt contains override-plan-review      -> pass (EM logs to STATE.md).
"""

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import paul_review  # noqa: E402

OVERRIDE_PHRASE = "override-plan-review"

# Reference to a PAUL plan file anywhere in the prompt. finditer is used so we
# can window the exec-intent check around each ref's position.
PLAN_REF_RE = re.compile(r"(\.paul/phases/[^\s'\"]+?-PLAN\.md)")

# Execution-intent signal words. These connote "run/apply the plan's tasks".
# Task-phrase verbs are PLURAL-AWARE (tasks?) so "complete Tasks 1-3" matches.
EXEC_INTENT_RE = re.compile(
    r"\b(implement|execute\s+(?:tasks?|the\s+plan)|complete\s+tasks?|apply|"
    r"build\s+tasks?|do\s+tasks?|write\s+the\s+code|run\s+the\s+plan|carry\s+out|"
    r"/paul:apply)\b",
    re.IGNORECASE,
)

# Verb-adjacent negation: a negation token IMMEDIATELY BEFORE a specific exec
# verb ("do not implement", "never apply") suppresses THAT verb only. It must
# modify the verb, not merely appear somewhere in the window. Checked against the
# ~30 chars preceding each exec-verb match.
NEGATION_RE = re.compile(
    r"\b(do\s+not|don'?t|never|no\s+need\s+to|without)\s*$",
    re.IGNORECASE,
)
NEGATION_LOOKBACK = 30  # chars before an exec verb to scan for a preceding negation

# Window (chars) on each side of a plan-ref within which exec-intent must appear.
# Bounds the match to the same clause/sentence region, not the whole prompt.
INTENT_WINDOW = 120


def _agent_text(event: dict) -> str:
    ti = event.get("tool_input", {})
    if not isinstance(ti, dict):
        return ""
    parts = [ti.get("prompt", ""), ti.get("description", "")]
    return "\n".join(p for p in parts if isinstance(p, str))


def _has_execution_intent(text: str, ref_start: int, ref_end: int) -> bool:
    """True iff a non-verb-adjacent-negated exec verb appears in the window
    around a plan-ref.

    Path B LEANS BLOCK: any genuine exec verb near the ref triggers, UNLESS a
    negation token immediately precedes that specific verb (so "Review <plan>;
    do NOT implement it" passes, but "Read <plan> and implement Task 1",
    "Implement <plan> without changing the API", and "Implement <plan> and
    summarize changes" all BLOCK — the negation/review words there do not modify
    the exec verb). Review framing alone does NOT suppress — a pure review
    dispatch has no exec verb near the ref, so it never fires.
    """
    lo = max(0, ref_start - INTENT_WINDOW)
    hi = min(len(text), ref_end + INTENT_WINDOW)
    window = text[lo:hi]
    for vm in EXEC_INTENT_RE.finditer(window):
        preceding = window[max(0, vm.start() - NEGATION_LOOKBACK):vm.start()]
        if NEGATION_RE.search(preceding):
            continue  # negation immediately before THIS verb — suppress it
        return True  # a genuine, non-negated exec verb near the ref → block
    return False


def main() -> None:
    if os.environ.get("PAUL_APPLY_GATE_DISABLE") == "1":
        return

    try:
        event = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError, TypeError):
        return
    if not isinstance(event, dict) or event.get("tool_name") != "Agent":
        return

    text = _agent_text(event)
    if not text:
        return

    if OVERRIDE_PHRASE in text:
        return  # bounded, logged override (EM logs a STATE.md Decisions row)

    # Window the exec-intent check around EACH plan-ref. A ref with a genuine
    # (non-verb-adjacent-negated) exec verb near it is enforced (lean-block).
    for m in PLAN_REF_RE.finditer(text):
        ref = m.group(1)
        if not _has_execution_intent(text, m.start(), m.end()):
            continue  # no genuine exec verb near this ref — do NOT block
        plan_path = paul_review.resolve_plan_arg(ref, Path.cwd())
        ok, status, detail = paul_review.validate_review(plan_path)
        if not ok:
            reason = (
                f"BLOCKED: dispatching an implementer to execute a PAUL plan "
                f"requires a fresh Codex plan-review PASS.\n"
                f"Plan: {plan_path}\n"
                f"Status: {status}\n"
                f"{detail}\n"
                f"To override: re-dispatch with `override-plan-review <reason>` "
                f"AND log a STATE.md `### Decisions` row: "
                f"`| <date>: Override — APPLY without Codex plan PASS (<reason>) "
                f"| Skipped plan-review gate for {plan_path.name} "
                f"| Proceeding with warning |`"
            )
            print(json.dumps({"decision": "block", "reason": reason}))
            return  # first non-OK execution-intent plan owns the block


if __name__ == "__main__":
    main()
