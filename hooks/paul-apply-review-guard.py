#!/usr/bin/env python3
"""Path A fence: block /paul:apply <plan> when no fresh Codex PASS exists.

UserPromptSubmit hook. Reads {"prompt": "..."} on stdin. If the prompt is a
/paul:apply invocation for a plan lacking a valid Codex PASS artifact, emits
{"decision":"block","reason":...} on stdout and exits 0. Otherwise silent pass.

Fail-closed on validation, but framing-first: a non-apply prompt, a no-arg
apply, the override phrase, or the disable env var all PASS silently.

Escape hatches:
  PAUL_APPLY_GATE_DISABLE=1        -> early return, no block (debug/teardown).
  prompt contains override-plan-review -> pass (apply.md logs the override).
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import paul_review  # noqa: E402

OVERRIDE_PHRASE = "override-plan-review"


def main() -> None:
    if os.environ.get("PAUL_APPLY_GATE_DISABLE") == "1":
        return  # disabled: pass silently

    try:
        event = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError, TypeError):
        return  # unparseable event: do not block a prompt on our account
    if not isinstance(event, dict):
        return

    prompt = event.get("prompt", "")
    if not isinstance(prompt, str) or not prompt:
        return

    match = paul_review.APPLY_RE.match(prompt)
    if match is None:
        return  # not a /paul:apply prompt

    if OVERRIDE_PHRASE in prompt:
        return  # bounded, logged override (apply.md writes STATE.md row)

    plan_arg = match.group(1)
    if not plan_arg:
        return  # no plan arg: command's own validate_plan handles it

    plan_path = paul_review.resolve_plan_arg(plan_arg, Path.cwd())
    ok, status, detail = paul_review.validate_review(plan_path)
    if ok:
        return  # valid Codex PASS: allow

    reason = (
        f"BLOCKED: /paul:apply requires a fresh Codex plan-review PASS.\n"
        f"Plan: {plan_path}\n"
        f"Status: {status}\n"
        f"{detail}"
    )
    print(json.dumps({"decision": "block", "reason": reason}))


if __name__ == "__main__":
    main()
