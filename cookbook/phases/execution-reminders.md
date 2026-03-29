# Execution Phase Reminders

> Loaded by the orchestrator from `cookbook/phases/execution.md` at reminder points during Phase 5. These are VERBATIM templates — print them as-is with values substituted.

## Pre-Execution Gate

Before dispatching the FIRST task, verify:

> **Pre-execution check:** Did you offer `/second-opinion review` on the plan? If Codex is available and you did not ask, STOP and go back to `cookbook/phases/planning-next-steps.md` step 3. The second-opinion gate is mandatory regardless of plan size.
>
> Known rationalization: "The plan was already approved" — approval and second-opinion are independent gates.

## Mid-Phase Reminders

During execution, after every 3 completed tasks, print a context check VERBATIM (substitute actual values):

> ---
> **Progress:** Completed {N} of {total} tasks. Tasks 1-{N} committed and verified.
>
> **Next:** Task {N+1}: {name}
>
> [Only if context `used_percentage` is above 60%:]
> **Context at N%.** Clear and resume: `/clear` then `/coding-team continue`
> ---

Also print on each mid-phase reminder:

> **Orchestrator check:** You are the orchestrator. If you have been writing code directly, stop and re-dispatch through Agent tool or Teammate tool. Direct edits bypass the audit loop.

Optionally run `mcp__codesight-mcp__get_usage_stats` with `session: "current"` to check which codesight tools agents are using. If key tools (get_callers, search_symbols, get_changes) show zero calls after 3+ tasks, agents may not be using code intelligence — consider including explicit tool reminders in subsequent implementer prompts.

## Debugging Detour Reminders

When the execution loop enters the `/debug` protocol (task failure, unexpected behavior), print:

> ---
> **Entering debug mode** for Task {N}.
>
> `/scope-lock <directory>` — lock edits to the affected module (prevents accidental changes elsewhere)
> `/debug` protocol: investigate -> analyze -> hypothesize -> implement
> `/parallel-fix` — if 3+ independent failures surface, dispatch parallel investigation teams
>
> When resolved, the execution loop will resume at the audit stage for this task.
> ---

When the debug detour completes and execution resumes, print:

> ---
> **Debug resolved.** Resuming execution at Task {N} audit.
>
> `/scope-unlock` — remove the edit boundary
> `/verify` — run the full test suite to confirm the fix didn't break anything
> ---

## Post-Execution Checklist

After the LAST task in the plan passes its audit, print this checklist VERBATIM before doing anything else:

> ---
> **All {N} tasks complete.** Before Phase 6, these steps are MANDATORY:
>
> 1. **Full-suite verification** — Run complete test suite + linter. All must pass.
> 2. **Feature-Level QA Review** — Dispatch `ct-qa` per the "Feature-Level QA Review" section in `execution.md`. Skip ONLY if 1 task AND ≤3 files changed.
> 3. **Doc-drift scan** — Read `cookbook/phases/doc-drift-scan.md` and follow.
> 4. **Post-execution review** — Read `cookbook/phases/post-execution-review.md` and follow (risk signals + second-opinion gate).
>
> Do NOT proceed to Phase 6 until all 4 steps are done.
> ---

**Named rationalizations (compliance triggers):**
- "All tasks passed their per-task audits" — per-task audits catch per-task bugs. Feature-level QA catches integration bugs between tasks. These are different quality dimensions.
- "The test suite already passed after each task" — per-task test runs verify individual tasks. The full-suite run after ALL tasks catches cross-task integration failures.
- "This is a small feature, QA is overkill" — the skip condition is explicit: 1 task AND ≤3 files. A 45-task job with 5 batches does not qualify. If in doubt, run QA.
- "I'll do the second-opinion later" — the post-execution review gate exists to catch issues BEFORE Phase 6 completion. Later means never under context pressure.
