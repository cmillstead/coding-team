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

**If AGENT_TEAMS_AVAILABLE = true:**
1. Create a team for the execution phase: `Teammate({ operation: "spawnTeam", team_name: "exec-<feature>" })`
2. For each task: create a task on the shared task list via `TaskCreate`, then spawn an implementer teammate
3. After implementer completes: spawn audit teammates (spec-reviewer, simplify, harden) — all Explore mode
4. Read results from inbox and task list
5. Decide what to do next (re-dispatch, proceed, escalate)
6. Shutdown and cleanup after all tasks complete

**If AGENT_TEAMS_AVAILABLE = false:**
1. Dispatch implementer using the Agent tool
2. Dispatch audit agents in parallel using the Agent tool
3. Read their results
4. Decide what to do next

If you catch yourself using Edit, Write, or running test commands directly — STOP. You are doing the implementer's job. Spawn a teammate (or Agent if teams unavailable) instead.

## Execution Loop

**If AGENT_TEAMS_AVAILABLE = true:**

Create one execution team for the entire phase:
`Teammate({ operation: "spawnTeam", team_name: "exec-<feature>" })`

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

  IMPLEMENTER
  2. Create task: TaskCreate({ subject: "Task N: <name>", description: "<full task text + context>", activeForm: "Implementing..." })
  3. Spawn implementer teammate with: full task text, context, working directory, baseline test state
     - Use model tier from plan
     - Do NOT make implementer read plan file — provide full text in spawn prompt
  4. Monitor for completion or messages. Handle status (see Implementer Status Protocol below).

  AUDIT TEAM (only if implementer reports DONE or DONE_WITH_CONCERNS)
  5. Record HEAD_SHA, collect modified files list (git diff --name-only BASE..HEAD)
  6. Spawn 3 audit teammates IN PARALLEL (all Explore mode):
     a. Spec reviewer (see prompts/spec-reviewer.md) — "does it match the spec? was TDD followed?"
     b. Simplify auditor (see prompts/simplify-auditor.md) — "is there a simpler way?"
     c. Harden auditor (see prompts/harden-auditor.md) — "what would an attacker try?"
     Each auditor messages team-lead with findings.
  7. Triage findings from inbox (see Audit Triage below)
  8. If findings to fix: spawn new implementer teammate to fix → re-audit (max 3 rounds)
     Fresh audit teammates each round — don't reuse.

  COMPLETENESS CHECK
  9. Compare implementer's output against every step in the task.
     For each step: was it done, skipped, or partially done?
     If ANY step was skipped or partially done without explanation:
     → re-dispatch implementer with "you missed steps X, Y — complete them"
     Do NOT proceed to audit with incomplete work.

  GATE
  10. VERIFY: run test suite, confirm pass with fresh output
  11. Shutdown task teammates (implementer + auditors)
  12. Next task

After all tasks: shutdown all remaining teammates, cleanup team.
```

**If AGENT_TEAMS_AVAILABLE = false:**

Same loop structure, but using Agent tool for dispatch instead of Teammate/TaskCreate:
- Step 2-3: dispatch implementer via Agent tool with full task text
- Step 6: dispatch audit agents in parallel via Agent tool (all Explore)
- Step 8: dispatch new Agent for fixes
- No shutdown/cleanup needed (agents terminate on completion)

**Audit teammates/agents MUST be read-only (Explore).** This prevents reviewers from silently "fixing" things instead of flagging them. The separation between finding and fixing is the whole point.

**Fresh audit teammates each round.** Don't reuse auditors — carried context biases toward "already checked" areas.

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

At every phase transition and before any completion claim, follow the `/verify` skill (`skills/verify/SKILL.md`). No "should pass," no "looks correct," no trusting agent reports without independent verification.

## Coordination Mode

When AGENT_TEAMS_AVAILABLE = true: all execution dispatch uses agent teams. One team per execution phase. Implementers and auditors are teammates. The main agent monitors via inbox and task list.

When AGENT_TEAMS_AVAILABLE = false: all execution dispatch uses the Agent tool.

In BOTH modes: the main agent never writes code directly.
