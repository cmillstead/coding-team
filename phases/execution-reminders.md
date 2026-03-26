# Execution Phase Reminders

> Loaded by the orchestrator from `phases/execution.md` at reminder points during Phase 5. These are VERBATIM templates — print them as-is with values substituted.

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
