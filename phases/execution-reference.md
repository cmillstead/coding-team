# Execution Reference

On-demand detail extracted from `phases/execution.md`.

## Implementer Status Protocol

The implementer on each task team reports one of four statuses:

**DONE:** Proceed to spec compliance review.

**DONE_WITH_CONCERNS:** Read the concerns. If about correctness or scope, address before review. If observational ("this file is getting large"), note and proceed.

**NEEDS_CONTEXT:** Provide missing context and re-dispatch.

**BLOCKED:** Assess the blocker:
1. Context problem -> provide the missing context, re-dispatch the implementer
2. Needs more reasoning -> split the task into smaller steps and re-dispatch, or add worked examples / exact code to the task text; do NOT change the agent's model — every agent inherits the session model
3. Task too large -> break into smaller pieces
4. Plan itself is wrong -> escalate to user

**Never** ignore an escalation, and never re-dispatch an identical prompt — every re-dispatch must change the task text, the context, or the scope.

## When Tasks Fail: Debugging Protocol

When a task fails during execution, follow the `/debug` skill (`skills/debug/SKILL.md`). Iron law: no fixes without root cause investigation.

## Verification Gates

At every phase transition and before any completion claim, follow the `/verify` skill (`skills/verify/SKILL.md`). No "should pass," no "looks correct," no trusting agent reports without independent verification.

## Coordination Mode

Execution uses **subagents** (Agent tool) for implementer and audit dispatch — these are independent, pre-decomposed tasks where COORDINATION=no.

**Exception:** If debugging reveals 3+ competing hypotheses with cross-cutting evidence potential (COORDINATION=yes), the `/debug` skill may escalate to agent teams. See `skills/debug/SKILL.md`.

In ALL modes: the main agent never writes code directly.

---

## Mid-Phase Reminders

After every 3 completed tasks, read `phases/execution-reminders.md` and print the progress template. Also print the orchestrator self-check.

## Debugging Detour Reminders

When entering or exiting the debug protocol, read `phases/execution-reminders.md` and print the appropriate template.
