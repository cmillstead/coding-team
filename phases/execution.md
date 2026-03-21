# Phase 5: Execution

Present to user:

> "Design and plan complete. Ready to execute?"
>
> If the task is non-trivial, offer a worktree: "Want me to set up an isolated worktree for this?"

## Worktree Setup (optional)

If user wants isolation (or task warrants it), follow the `/worktree` skill (`skills/worktree/SKILL.md`).

## Task-by-Task Execution

On approval, begin execution. **Agent team per task: implementer + audit team (spec + simplify + harden).** Implementer follows the `/tdd` skill for all implementation work.

**CRITICAL: The main agent is the orchestrator, not the implementer.** You do NOT write code, edit files, or run tests yourself during Phase 5. Your ONLY permitted tools during execution are:
- **Agent tool** — dispatch implementer and auditor subagents
- **Teammate tool** — dispatch teammates (if agent teams available)
- **SendMessage tool** — coordinate with teammates
- **TaskCreate / TaskList / TaskUpdate tools** — manage shared task list
- **Read tool** — read files for context (NEVER edit them)
- **Bash tool for git commands only** — `git diff`, `git log`, `git rev-parse` (NOT test commands, NOT `pytest`, NOT `npm test`, NOT `cargo test`)

If you use Edit, Write, or Bash to run tests during Phase 5, the task must be re-done by an agent. Your direct edit bypasses the audit loop and is not trusted — it skips spec review, simplify audit, and harden audit. Unreviewed code does not ship.

**Why subagents for execution:** Evaluate the three signals (see SKILL.md Step 0):
- **Implementer dispatch:** COORDINATION=no (one implementer per task, owns distinct files per plan), DISCOVERY=no (plan specifies exact changes), COMPLEXITY=varies but independent → **subagents**
- **Audit dispatch:** COORDINATION=no (read-only reviewers examine same diff independently, report to lead), DISCOVERY=no (scope is the diff), COMPLEXITY=yes but independent → **subagents**

Execution uses subagents because the plan pre-decomposes work into independent tasks. Each agent works alone and reports back.

## Execution Loop

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
  2. Dispatch implementer via Agent tool — use model tier from the plan
     - Pass: full task text, context, working directory, baseline test state
     - If the task has advisory skills: include the advisory block in the implementer prompt's Advisory Skills section. The implementer applies these rules throughout implementation.
     - Do NOT make implementer read plan file — provide full text
  3. Handle implementer status (see Implementer Status Protocol below)

  AUDIT TEAM (only if implementer reports DONE or DONE_WITH_CONCERNS)
  4. Record HEAD_SHA, collect modified files list (git diff --name-only BASE..HEAD)
  5. Dispatch audit agents IN PARALLEL via Agent tool (all read-only Explore):
     a. Spec reviewer (see prompts/spec-reviewer.md) — "does it match the spec? was TDD followed?"
     b. Simplify auditor (see prompts/simplify-auditor.md) — "is there a simpler way?"
     c. Harden auditor (see prompts/harden-auditor.md) — "what would an attacker try?"
     d. Prompt-craft auditor (see prompts/prompt-craft-auditor.md) — triggers when BOTH:
        (i) Task has PROMPT_CRAFT_ADVISORY annotation, AND
        (ii) Modified files include at least 1 file matching: `phases/*.md`, `prompts/*.md`, `skills/*/SKILL.md`, `SKILL.md`, `CLAUDE.md`, `memory/*.md`
        Both conditions required (belt and suspenders). If either is missing, skip this auditor.
  6. Triage findings (see Audit Triage below)
  7. If findings to fix → dispatch new implementer to fix → re-audit (max 3 rounds)
     Fresh audit agents each round — don't reuse.

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

## Documentation Drift Scan (after all tasks)

After plan completeness verification passes and before proceeding to Phase 6, check for documentation drift across the full diff.

**Skip this scan when:**
- The feature only modified test files (no behavior change to document)
- Every implementer reported "No doc impact" for all tasks
- The plan explicitly noted "no documentation surface" in the NOT in scope section

**When NOT skipping:**

1. **Pre-filter doc files that reference changed code:**
   ```bash
   REPO_ROOT=$(git rev-parse --show-toplevel)
   CHANGED=$(git diff $(git merge-base HEAD main) --name-only)
   DOC_FILES=$(find "$REPO_ROOT" -maxdepth 3 -name "*.md" -not -path "*/.git/*" -not -path "*/node_modules/*")
   # Find doc files that mention any changed file stem
   echo "$CHANGED" | sed 's|.*/||; s|\.[^.]*$||' | sort -u | while read stem; do
     grep -l "$stem" $DOC_FILES 2>/dev/null
   done | sort -u
   ```

2. **Dispatch a doc-review agent via Agent tool (read-only Explore, model: sonnet):**

   Pass the agent: the pre-filtered doc files list AND the actual diff summary (`git diff $(git merge-base HEAD main) --stat` plus key changes).

   Agent prompt:
   > Review these documentation files against the branch changes.
   >
   > Changed files with summary: [diff stat + key changes]
   > Doc files that reference changed code: [pre-filtered list]
   >
   > For each doc file, identify:
   > - Stale file paths (references to renamed, moved, or deleted files)
   > - Stale descriptions (behavior changed but docs describe the old way)
   > - Missing entries (new files, features, or APIs not yet documented)
   >
   > Report format:
   > - MUST_FIX: [doc file]: [what's stale] → [what it should say]
   > - NICE_TO_HAVE: [doc file]: [minor improvement]
   > - Or: "No drift detected"
   >
   > Do NOT make changes. Report only.

3. **If MUST_FIX findings:** dispatch an implementer via Agent tool to fix the doc issues as a single task.

4. **If only NICE_TO_HAVE or no drift:** proceed to Phase 6. Note NICE_TO_HAVE items in the completion summary for `/document-release` to pick up.

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

During execution, after every 3 completed tasks, print a context check VERBATIM (substitute actual values):

> ---
> **Context check:** Completed {N} of {total} tasks.
>
> **Continue:** next task is Task {N+1}: {name}
> **Clear and resume:** `/clear` then `/coding-team continue` — the router will find the plan and resume at Task {N+1}
>
> Progress so far: Tasks 1-{N} committed and verified.
> ---

Also print on each mid-phase reminder:

> **Orchestrator check:** You are the orchestrator. If you have been writing code directly, stop and re-dispatch through Agent tool or Teammate tool. Direct edits bypass the audit loop.

## Debugging Detour Reminders

When the execution loop enters the `/debug` protocol (task failure, unexpected behavior), print:

> ---
> **Entering debug mode** for Task {N}.
>
> `/freeze <directory>` — lock edits to the affected module (prevents accidental changes elsewhere)
> `/debug` protocol: investigate -> analyze -> hypothesize -> implement
>
> When resolved, the execution loop will resume at the audit stage for this task.
> ---

When the debug detour completes and execution resumes, print:

> ---
> **Debug resolved.** Resuming execution at Task {N} audit.
>
> `/unfreeze` — if you used `/freeze`, remove the edit boundary now
> ---

## Next Steps

After all tasks are executed and verified, print this block VERBATIM:

> ---
>
> **All tasks executed and verified.**
>
> **Next:** Phase 6 completion. "Proceed to Phase 6"
>
> **Recommended before completion:**
> - `/codex review` — cross-model review of the full diff (findings overlap with Claude's audit = high confidence)
> - `/codex challenge` — adversarial review (recommended for auth, payment, encryption, data deletion changes)
> - `/verify` — if you want to independently re-run the full test suite before proceeding
>
> **Preview — offered again in Phase 6:**
> - `/retro` — engineering retrospective
> - `/document-release` — update docs to match shipped code
> - `/prompt-craft audit` — if this feature changed any skills or prompts
>
> **Shipping shortcut:** `/ship` for a fully automated release instead of the manual Phase 6 flow.
>
> ---
