# Phase 5: Execution

Present to user:

> "Design and plan complete. Ready to execute?"
>
> If the task is non-trivial, offer a worktree: "Want me to set up an isolated worktree for this?"

## Worktree Setup (optional)

If user wants isolation (or task warrants it), follow the `/worktree` skill (`skills/worktree/SKILL.md`).

## Task-by-Task Execution

On approval, begin execution. **Agent team per task: implementer + audit team (spec + simplify + harden).** Implementer follows the `/tdd` skill for all implementation work.

**CRITICAL: The main agent is the orchestrator, not the implementer.** During Phase 5, you dispatch all file edits to agents. Your ONLY permitted direct actions are:
- **Agent tool** — dispatch implementer and auditor subagents
- **Teammate tool** — dispatch teammates (if agent teams available)
- **SendMessage tool** — coordinate with teammates
- **TaskCreate / TaskList / TaskUpdate tools** — manage shared task list
- **Read tool** — read files for context
- **Edit/Write tools** — ONLY for `memory/`, `~/Documents/obsidian-vault/`, and `/tmp/` session files. All other edits — including `agents/`, `phases/`, `prompts/`, `skills/`, `hooks/`, `docs/plans/`, and source code — go through the Agent tool. See "Phase 5 Edit Routing" in SKILL.md.
- **Bash tool for git commands only** — `git diff`, `git log`, `git rev-parse` (NOT test commands, NOT `pytest`, NOT `npm test`, NOT `cargo test`)

If you use Edit, Write, or Bash to run tests during Phase 5, the task must be re-done by an agent. Your direct edit bypasses the audit loop and is not trusted — it skips spec review, simplify audit, and harden audit. Unreviewed code does not ship.

During Phase 5, spawn subagents for all code changes.

**Why subagents for execution:** Evaluate the three signals (see SKILL.md Step 0):
- **Implementer dispatch:** COORDINATION=no (one implementer per task, owns distinct files per plan), DISCOVERY=no (plan specifies exact changes), COMPLEXITY=varies but independent → **subagents**
- **Audit dispatch:** COORDINATION=no (read-only reviewers examine same diff independently, report to lead), DISCOVERY=no (scope is the diff), COMPLEXITY=yes but independent → **subagents**

Execution uses subagents because the plan pre-decomposes work into independent tasks. Each agent works alone and reports back.

**Pre-flight: Feature branch.** Before dispatching the first implementer, verify the current branch is not main/master. If on main, create a feature branch: `git checkout -b <feature-name>`. All Phase 5 work happens on this branch.

**Pre-flight: Session state.** Write the session state file so execution-phase hooks activate:

```bash
python3 -c "import json, time; json.dump({'phase': 'execution', 'ts': time.time()}, open('/tmp/coding-team-session.json', 'w'))"
```

This activates:
- `phase5-edit-guard.py` — warns if the orchestrator edits code directly instead of delegating
- `plan-completeness-check.py` — warns if agent output covers fewer findings than assigned

The file auto-expires after 2 hours. Clean up is not required but can be done in Phase 6.

## Execution Loop

```
BASELINE (once, before first task)
  CODESIGHT INDEX CHECK (once, before first task)
  -1. Verify the repo is indexed for codesight-mcp:
      Run `mcp__codesight-mcp__list_repos` to see indexed repos.
      If the working directory's repo is NOT listed, run `mcp__codesight-mcp__index_folder` with the working directory path.
      If the repo IS listed, run `mcp__codesight-mcp__get_status` to verify the index is current. If the index is stale (status shows outdated or files changed since last index), run `mcp__codesight-mcp__index_folder` to reindex. Do NOT fall back to Grep/Bash when the index is stale — reindex instead.
      If codesight-mcp tools are not available (MCP server not running), skip — agents will fall back to Grep/Read.
      If a codesight-mcp call fails or times out, fall back to Grep/Read for that specific query. Do NOT block on a flaky MCP connection.

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

  IMPLEMENTER (see ~/.claude/agents/ct-implementer.md)
  2. Dispatch implementer via Agent tool — use model tier from the plan
     - Pass: full task text, context, working directory, baseline test state
     - If the task has advisory skills: include the advisory block in the implementer prompt's Advisory Skills section. The implementer applies these rules throughout implementation.
     - If the task involves Python, TypeScript, Angular, JavaScript, HTML, or SCSS files, read `~/.claude/code-style.md` using the Read tool and include its contents in the implementer prompt's Code Style section.
     - Read `~/.claude/golden-principles.md` and include in the implementer prompt's Context section when the task involves architectural decisions or new patterns.
     - If `$REPO_ROOT/docs/team-memory.md` exists, read it and include relevant entries in the implementer prompt's Context section — especially known landmines and past decisions.
     - Do NOT make implementer read plan file — provide full text
  3. Handle implementer status (see Implementer Status Protocol below)

  COMPLETENESS CHECK (MANDATORY — do NOT skip under context pressure)
  4. Compare implementer's output against every step AND every enumerated item in the task.
     a. Count the items in the task spec (files to modify, hooks to migrate, tests to write, etc.)
     b. Count the items the implementer reports as completed
     c. If report_count < spec_count: re-dispatch with "you processed M of N items — complete the remaining: [list missing items]"
     d. For each step: was it done, skipped, or partially done?
     e. If ANY step was skipped or partially done without explanation:
        → re-dispatch implementer with "you missed steps X, Y — complete them"
     Do NOT proceed to audit with incomplete work.
     Known rationalization: "The agent reported DONE so it must be complete" — DONE is a claim, not evidence. Verify the count.

  AUDIT PASS
  Read `phases/audit-loop.md` and follow its instructions for the audit pass.

  SECURITY ESCALATION (after audit loop, before gate)
  8.5. Check if the task touches security-sensitive files:
       ```bash
       git diff --name-only BASE..HEAD | grep -iE "auth|payment|encrypt|session|token|cors|csp|secret|credential|permission"
       ```
       - If 1-2 matches: note in completion summary for user awareness.
       - If 3+ matches OR any harden auditor finding is CRITICAL: dispatch `/scan-security` (`skills/scan-security`) as an additional review gate via Agent tool (model: sonnet). Pass the full diff and harden auditor findings.
       - If 5+ matches OR 2+ CRITICAL harden findings: recommend `/scan-adversarial` to the user before proceeding.
       - If zero matches: skip and note in status: 'No security-sensitive files detected — skipped'

  GATE
  9. VERIFY: Dispatch a verification subagent to re-run tests independently.
     If context budget is exhausted (>80%), accept the implementer's reported
     output as fallback.
  10. Mark task complete
  11. Next task
```

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

**Full-suite verification:** Run the complete test suite and linter after ALL tasks complete. This catches integration failures between tasks that per-task GATE checks miss. All tests must pass and linter must be clean before proceeding.

## Feature-Level QA Review (after full-suite verification)

After all tasks pass and the full test suite is clean, dispatch the QA reviewer to check the **complete feature diff** holistically. This catches integration issues, dark features, and behavioral gaps that per-task auditors miss.

1. Collect the full feature diff:
   ```bash
   BASE=$(git merge-base HEAD main 2>/dev/null || git merge-base HEAD master)
   git diff --stat $BASE..HEAD
   git diff --name-only $BASE..HEAD
   ```
2. Dispatch the QA reviewer via Agent tool (model: sonnet, subagent_type: Explore — read-only):
   - Pass: feature description (from the original plan), full diff summary, list of all modified files, and the list of tasks that were executed
   - See `~/.claude/agents/ct-qa-reviewer.md` for the full prompt template
3. Triage QA findings using the same severity routing as the audit loop:
   - **HIGH** (integration mismatch, dark feature, behavioral bug) → dispatch implementer to fix, then re-run full test suite
   - **MEDIUM** (edge case, test gap) → include in a fix round
   - **LOW** (minor test gap for non-critical path) → note in completion summary
4. If the QA reviewer reports FAIL or has 2+ HIGH findings: fix all HIGH/MEDIUM findings before proceeding. Max 2 fix rounds for QA findings.
5. If the QA reviewer reports PASS or PASS_WITH_CONCERNS with no HIGH findings: proceed.

**Skip condition:** If the feature has only 1 task AND touches 3 or fewer files, the per-task audit is sufficient — skip the QA review. Feature-level QA adds value when multiple tasks interact.

Read `phases/doc-drift-scan.md` and follow its instructions.

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

## Next Steps

After all tasks are executed and verified, read `phases/post-execution-review.md` and follow its instructions. It handles risk signal evaluation, optional Codex review, and the completion handoff to Phase 6.
