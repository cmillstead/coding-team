# Phase 5: Execution

Present to user:

> "Design and plan complete. Ready to execute?"
>
> If the task is non-trivial, offer a worktree: "Want me to set up an isolated worktree for this?"

## Worktree Setup (optional)

If user wants isolation (or task warrants it), follow the `/worktree` skill (`skills/worktree/SKILL.md`).

## Task-by-Task Execution

On approval, begin execution. **Agent team per task: implementer + audit team (spec + simplify + harden).** Implementer follows the `/tdd` skill for all implementation work.

**CRITICAL: The main agent is the orchestrator, not the implementer.** You do NOT write code, edit files, or run tests yourself during Phase 5. Your job is to:
1. Dispatch subagents (implementer, auditors) using the Agent tool
2. Read their results
3. Decide what to do next (re-dispatch, proceed, escalate)

If you catch yourself using Edit, Write, or running test commands directly — STOP. You are doing the implementer's job. Spawn an Agent instead.

## Execution Loop

Each task gets its own **task team** — implementer builds, audit team reviews:

```
BASELINE (once, before first task)
  0. Run full test suite and record results as BASELINE_FAILURES
     - If all tests pass: baseline is clean
     - If tests fail: these are PRE-EXISTING failures that must be fixed
     - Pass BASELINE_FAILURES to every implementer

For each task in plan:
  1. Record BASE_SHA (git rev-parse HEAD)

  PRE-EXISTING FAILURES (if any remain from baseline)
  1a. The first implementer that encounters pre-existing failures MUST fix them
      before starting task work. This is non-negotiable — all tests must pass
      before new work begins. Include the failures in the implementer prompt
      as a "Fix before starting" section.
  1b. If pre-existing failures are in an unrelated area and the fix is non-trivial,
      treat it as a separate mini-task: investigate root cause, fix, verify, commit
      with "fix: resolve pre-existing test failure in <area>" before proceeding.

  IMPLEMENTER (see prompts/implementer.md)
  2. Dispatch implementer — use model tier from the plan
     - Pass: full task text, context, working directory, baseline test state
     - Do NOT make implementer read plan file — provide full text
  3. Handle implementer status (see below)

  AUDIT TEAM (only if implementer reports DONE or DONE_WITH_CONCERNS)
  4. Record HEAD_SHA, collect modified files list (git diff --name-only BASE..HEAD)
  5. Dispatch audit team IN PARALLEL (all read-only Explore agents):
     a. Spec reviewer (see prompts/spec-reviewer.md) — "does it match the spec? was TDD followed?"
     b. Simplify auditor (see prompts/simplify-auditor.md) — "is there a simpler way?"
     c. Harden auditor (see prompts/harden-auditor.md) — "what would an attacker try?"
  6. Triage findings (see Audit Triage below)
  7. If findings to fix -> implementer fixes -> re-audit (max 3 rounds)

  COMPLETENESS CHECK
  8. Compare implementer's output against every step in the task.
     For each step: was it done, skipped, or partially done?
     If ANY step was skipped or partially done without explanation:
     → re-dispatch implementer with "you missed steps X, Y — complete them"
     Do NOT proceed to audit with incomplete work.

  GATE
  9. VERIFY: run test suite, confirm pass with fresh output
  10. Mark task complete
  11. Next task
```

**Audit agents MUST be read-only (Explore).** This prevents reviewers from silently "fixing" things instead of flagging them. The separation between finding and fixing is the whole point.

**Fresh audit agents each round.** Don't reuse auditors — carried context biases toward "already checked" areas.

## Audit Triage

After collecting findings from all auditors:

**Refactor gate:** For any finding categorized as "refactor" (not a bug or security issue), apply this bar: *"Would a senior engineer say this is clearly wrong, not just imperfect?"* Reject style preferences and marginal improvements.

**Severity routing:**
- **Critical/High** — implementer fixes immediately, re-audit
- **Medium** — include in next fix round
- **Low/Cosmetic** — fix inline if trivial, otherwise note in completion summary and skip

**Budget check:** If fix rounds add 30%+ to the original implementation diff, tighten scope — skip medium/low simplify findings, focus on harden patches and spec gaps.

**Drift check (between audit rounds):** Before spawning the next audit round, re-read the original task description. If findings are pulling into unrelated areas or scope has expanded beyond the task, re-scope or exit the audit loop.

## Audit Loop Exit

Exit when ANY are true:
1. **Clean audit** — all auditors report zero findings
2. **Low-only round** — all remaining findings are low severity, fix inline
3. **Loop cap reached** — 3 audit rounds completed. Fix remaining critical/high inline, log unresolved medium/low in completion summary

## Implementer Status Protocol

The implementer on each task team reports one of four statuses:

**DONE:** Proceed to spec compliance review.

**DONE_WITH_CONCERNS:** Read the concerns. If about correctness or scope, address before review. If observational ("this file is getting large"), note and proceed.

**NEEDS_CONTEXT:** Provide missing context and re-dispatch.

**BLOCKED:** Assess the blocker:
1. Context problem -> provide more context, re-dispatch same model
2. Needs more reasoning -> re-dispatch with a more capable model
3. Task too large -> break into smaller pieces
4. Plan itself is wrong -> escalate to user

**Never** ignore an escalation or retry the same model without changes.

## Plan Completeness Verification (after all tasks)

Before declaring execution complete, verify the full plan was executed:

1. List every task from the plan.
2. For each task, confirm it was completed (has a commit) or explicitly skipped (with user approval).
3. If the plan has a traceability table (scan findings), verify every "Fix" row has a corresponding commit.
4. If any tasks were silently dropped, execute them now — do not proceed to Phase 6.

## When Tasks Fail: Debugging Protocol

When a task fails during execution, follow the `/debug` skill (`skills/debug/SKILL.md`). Iron law: no fixes without root cause investigation.

## Verification Gates

At every phase transition and before any completion claim, follow the `/verify` skill (`skills/verify/SKILL.md`). No "should pass," no "looks correct," no trusting agent team reports without independent verification.

## Agent Teams Routing (Execution Phase)

| Situation | Agent Teams? | Rationale |
|-----------|-------------|-----------|
| Task implementation | No | One implementer per task. Subagent. |
| Audit team (spec/simplify/harden) | No | Read-only reviewers report findings to lead. No inter-reviewer coordination needed. |
| Debugging: simple bug | No | Sequential, single agent. |
| Debugging: 2 hypotheses | No | Subagents suffice, overhead not justified. |
| Debugging: 3+ hypotheses with possible cross-cutting evidence | **Yes** | Scientific debate pattern. Investigators disprove each other in real time. |
| Parallel dispatch: 2 domains, provably independent | No | Subagents. |
| Parallel dispatch: 3+ domains, possibly shared infrastructure | **Yes** | Cross-domain discovery prevents wasted work on conflicting fixes. |

**Default is subagents.** Agent teams are the exception for specific high-value patterns, not the rule.
