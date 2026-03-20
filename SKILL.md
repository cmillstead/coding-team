---
name: coding-team
description: Use when starting any code task — new features, refactors, significant bug fixes, or any work that benefits from specialist design review. Also use as the session-start skill for code conversations — routes to the right workflow phase. Assembles a team of specialist agents to collaboratively design, plan, execute, verify, and ship. Self-contained — no dependency on superpowers skills.
---

# /coding-team — Specialist Agent Team for Code Tasks

End-to-end skill for code work: design, plan, execute, verify, ship. A specialist team collaboratively designs your feature, a planning worker produces an implementation plan, then execution runs task-by-task with two-stage review.

Use `/brainstorming` for business ideas, strategy, and non-code exploration.

---

## Session Start: Skill Router

When invoked at the start of a conversation (or when the user asks for help with a code task), determine the right entry point:

**Step 1: Check if this is a continuation.** If the user mentions a phase number, task number, feature name, "continue", "pick up where I left off", or any reference to prior work — this is a **resumed session**. Go to Step 2 before routing.

**Step 2: Discover existing plans.** You have NO memory of prior conversations. Do NOT guess filenames.

```
Glob docs/plans/*.md
```

- **No docs/plans/ directory or no .md files:** This is a fresh task. Route using the table below.
- **Files found:** Read each file's first 10 lines (title/header). Match the user's request to a plan by content, not filename. If ambiguous, show the user the list and ask which one. Then check `git log --oneline -20` for committed progress. Resume at the next incomplete task.

**Step 3: Route.** For fresh tasks (no prior plans), or after plan discovery:

| User's situation | Entry point |
|---|---|
| New feature idea, vague request | **Phase 1** — start dialogue |
| Has a design/spec, needs a plan | **Phase 4** — planning worker |
| Has a plan file, ready to build | **Phase 5** — execution |
| Bug report or test failure | **Debugging protocol** (`debugging-protocol.md`) |
| Existing PR with review feedback | **Review reception protocol** (`review-reception-protocol.md`) |
| Multiple independent failures | **Parallel dispatch** (`parallel-dispatch-protocol.md`) |
| Simple mechanical task (rename, format, single-file edit) | Skip coding-team — just do it directly |

**Don't force the full pipeline for tasks that don't need it.** A typo fix doesn't need 5 specialist workers. Match the process weight to the task weight. But for anything non-trivial, start at the appropriate phase.

---

## Guiding Principles

These apply to every agent in the team:

- **Scrap, don't fix** — if a worker's output is thin, off-scope, or clearly low quality, the Team Leader respawns it rather than patching around it. Bad agent output is an engineering problem, not a starting point.
- **Never mock what you can use for real** — tests must use real implementations wherever available. Only mock external systems that are genuinely unavailable in the test environment (remote APIs, third-party services). Never mock the thing being tested.
- **Quality gates before handoff** — no agent passes work to the next stage until tests pass and linting is clean. Build green -> commit -> move on.
- **Focused agents produce correct agents** — one worker, one lens, one scope. Workers that wander produce slop.
- **No ambiguity in specs** — the Planning Worker leaves nothing to inference. Exact file paths, exact line ranges, complete code snippets, exact commands with expected output.
- **Evidence before claims** — no completion claims without fresh verification output. If you haven't run the command in this message, you cannot claim it passes. See `verification-protocol.md`.
- **Right-size the model** — use the cheapest model that can handle the task. Haiku for mechanical edits, Sonnet for implementation, Opus for architecture and review.

---

## Phase 1: Dialogue (Main Claude)

1. Read project context — files, docs, recent commits, CLAUDE.md
2. Ask clarifying questions **one at a time** — multiple choice preferred, open-ended when needed
3. If upcoming questions involve visual content (mockups, layouts, diagrams), offer the visual companion as its own standalone message before continuing questions
4. Propose 2-3 approaches with trade-offs and your recommendation. Structure:
   - At least one **minimal viable** approach (fewest files, smallest diff)
   - At least one **ideal architecture** approach (best long-term trajectory)
   - For complex features, add a **dream state** sketch: current state → this plan → 12-month ideal
5. Get user approval on direction

Do NOT create the Team Leader until the user has approved an approach.

**Scope check:** If the request describes multiple independent subsystems, flag this immediately. Help decompose into sub-projects before detailed design. Each sub-project gets its own design -> plan -> execution cycle.

---

## Phase 2: Design Team

Create **one Team Leader task** using `TaskCreate` with: project summary, user's idea, approved approach, and all relevant context from Phase 1.

**Team Leader responsibilities:**

1. Decide which specialist workers to spawn, using the sizing heuristics below. Always explain the choice.
2. **Map skills to workers:**
   a. Read `~/.claude/skills/skill-taxonomy.yml`
   b. Identify which categories are relevant to the current task (match task description against category descriptions and skill use-cases)
   c. For each worker, filter to skills whose category lists that worker's role
   d. Build an advisory skill block for each worker's prompt (see format below)
3. Create workers simultaneously via `TaskCreate`. Pass each worker: full context + all sibling task IDs + an explicit **out-of-scope statement** (what this worker should NOT address) + their **skill advisory block**.
4. Wait for all workers (`TaskList`).
5. **Quality check** — before synthesizing, evaluate each worker's output. If a worker's output is off-scope, thin, or clearly low quality: respawn it with a more constrained prompt. Don't patch bad output — scrap and rerun.
6. Cross-review pass — create follow-up tasks where workers read sibling outputs via `TaskOutput(sibling_id)` and flag cross-domain concerns.
7. Synthesize into a design doc. Return it.

**Skill advisory block format (included in each worker's prompt):**

> ## Available Skills
>
> The following skills are installed and relevant to this task.
> Invoke any that would strengthen your analysis using the Skill tool.
>
> - `skill-name` — one-line description of when to use it

If no skills match a worker's role + the task's categories, omit the block for that worker.

**Specialist roles:**

| Role | Focus | Skip when |
|------|-------|-----------|
| Architect | System design, composability, data flow, fit with existing architecture | Trivial bug fixes |
| Senior Coder | Implementation approach, patterns, idiomatic code, complexity trade-offs | Never |
| UX/UI Designer | First-run UX, error messages, command discoverability, feedback, consistency | Pure backend / no user-facing surface |
| Tester | Test strategy, edge cases, what's hard to test, integration vs unit | Never |
| Security Engineer | Trust boundaries, input validation, threat model, new attack surface | Pure refactors with no new surface area |
| DevOps/Infra | CI/CD, deployment, containerization, observability, build pipeline | No deployment or infra changes |
| Data Engineer | Schema design, migrations, query performance, data modeling, pipelines | No data layer changes |
| Performance Engineer | Profiling, benchmarks, latency budgets, memory, algorithmic complexity | No performance-sensitive paths touched |
| Technical Writer | API docs, user guides, changelog, developer experience of documentation | No public-facing or doc surface |

**Team sizing heuristics:**

| Complexity | Design Workers | Signals |
|---|---|---|
| Simple (1-2 files) | 2 | Isolated bug, small feature, single concern |
| Moderate (3-10 files) | 3-4 | Multi-file changes, 2-3 concerns |
| Complex (10-30 files) | 4-6 | Cross-cutting concerns, large features |
| Very complex (30+ files) | 6-9 | Full-stack features, systemic changes |

Start with the smallest team that covers all required dimensions. More workers = more parallelism but more coordination overhead.

**Spawning examples:**
- New user-facing command -> Architect + Senior Coder + UX/UI + Tester + Security + Technical Writer
- Backend/CLI feature -> Architect + Senior Coder + Tester + Security
- Database-heavy feature -> Architect + Senior Coder + Data Engineer + Tester + Security
- Performance-sensitive feature -> Architect + Senior Coder + Performance Engineer + Tester
- Feature with CI/deploy changes -> Architect + Senior Coder + DevOps/Infra + Tester
- Refactor -> Architect + Senior Coder + Tester
- Bug fix -> Senior Coder + Tester (lightweight)
- New public API or tool -> Architect + Senior Coder + Tester + Security + Technical Writer

**Worker output format:**
- Findings from their specialist lens
- Concerns or risks with the proposed approach
- Recommendations and alternatives
- Cross-domain flags after reading sibling outputs

**Team Leader synthesis:**
- Resolve conflicts between workers
- Produce design doc covering: architecture, components, data flow, error handling, testing strategy, security considerations
- Flag unresolved trade-offs for user decision

---

## Phase 3: Design Approval + Spec Review

Main Claude presents the synthesized design doc. Get explicit approval. Revise if needed.

**After user approval, write and review the spec:**

1. Write spec to `docs/plans/YYYY-MM-DD-<feature>-design.md`
2. Dispatch spec-document-reviewer agent (see `prompts/spec-doc-reviewer.md`)
3. If Issues Found: fix, re-dispatch, repeat (max 3 iterations, then surface to user)
4. If Approved: present spec to user for final review before proceeding
5. Only proceed to Phase 4 after user confirms the written spec

---

## Phase 4: Planning Worker

Create a **Planning Worker task** with: design doc + full project context.

Worker is Architect + Senior Coder. Produces implementation plan.

### Step 0: Scope Challenge (before planning)

Before writing tasks, the planning worker must answer:

1. **What existing code already solves sub-problems?** Can we reuse rather than rebuild?
2. **What is the minimum set of changes?** Flag work that could be deferred without blocking the core goal.
3. **Complexity smell:** If the plan touches 8+ files or introduces 2+ new classes/services, challenge whether the same goal can be achieved with fewer moving parts.

### Plan Document Format

Every plan starts with this header:

```markdown
# [Feature Name] Implementation Plan

**Goal:** [One sentence describing what this builds]

**Architecture:** [2-3 sentences about approach]

**Tech Stack:** [Key technologies/libraries]

---
```

### File Structure

Before defining tasks, map out which files will be created or modified and what each one is responsible for. Design units with clear boundaries and well-defined interfaces. Prefer smaller, focused files.

### Task Structure

````markdown
### Task N: [Component Name]

**Files:**
- Create: `exact/path/to/file.py`
- Modify: `exact/path/to/existing.py:123-145`
- Test: `tests/exact/path/to/test.py`

**Model:** haiku | sonnet | opus

- [ ] **Step 1: Write the failing test**

```python
def test_specific_behavior():
    result = function(input)
    assert result == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/path/test.py::test_name -v`
Expected: FAIL with "function not defined"

- [ ] **Step 3: Write minimal implementation**

```python
def function(input):
    return expected
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/path/test.py::test_name -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/path/test.py src/path/file.py
git commit -m "feat: add specific feature"
```
````

**Each step is one action (2-5 minutes).** Complete code in plan — not "add validation here." Exact commands with expected output.

**Model assignment per task:** The planning worker assigns a model tier to each task:
- **haiku** — touches 1-2 files with complete spec, mechanical changes
- **sonnet** — touches multiple files, needs judgment, integration work
- **opus** — requires design decisions, broad codebase understanding

**Testing rules baked into every plan:**
- Never mock what you can use for real
- Only mock external systems genuinely unavailable in test environment
- Never mock the thing being tested
- Every task batch ends with: run tests -> run linter -> confirm both pass -> commit

### Required Plan Sections

Beyond the task list, every plan must include:

**Failure modes** — for each new codepath or integration point:

| Codepath | Failure mode | Tested? | Error handling? | User sees |
|---|---|---|---|---|
| `module.function` | timeout on external call | ? | ? | ? |

Any row with tested=no AND error handling=no AND user sees=silent → **critical gap** that must be addressed in a task.

**NOT in scope** — work considered and explicitly deferred, with one-line rationale each. Prevents scope creep and captures ideas for future work.

**What already exists** — existing code/flows that partially solve sub-problems and whether the plan reuses them.

### Quality gate — self-review before returning

1. Pick 3 tasks at random — could a developer implement each without asking a single question?
2. Are all file references exact (`src/config.rs:14`, not "the config file")?
3. Does every feature task have a corresponding test task?
4. Are there security implications not addressed?
5. Is there any step that silently assumes context the implementer won't have?
6. Does the failure modes table have any critical gaps (no test + no handling + silent)?

### Plan Review Loop

After writing the plan:

1. Dispatch plan-document-reviewer agent (see `prompts/plan-doc-reviewer.md`)
2. If Issues Found: fix, re-dispatch (max 3 iterations, then surface to user)
3. If Approved: save plan and proceed

Save plan to: `docs/plans/YYYY-MM-DD-<feature>.md`

---

## Phase 5: Execution

Present to user:

> "Design and plan complete. Ready to execute?"
>
> If the task is non-trivial, offer a worktree: "Want me to set up an isolated worktree for this?"

### Worktree Setup (optional)

If user wants isolation (or task warrants it), follow `worktree-protocol.md`:
1. Find or create worktree directory
2. Verify it's gitignored
3. Create worktree with feature branch
4. Run project setup and verify clean baseline

### Task-by-Task Execution

On approval, begin execution. **Agent team per task: implementer + audit team (spec + simplify + harden).**

### Execution Loop

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

  GATE
  8. VERIFY: run test suite, confirm pass with fresh output
  9. Mark task complete
  10. Next task
```

**Audit agents MUST be read-only (Explore).** This prevents reviewers from silently "fixing" things instead of flagging them. The separation between finding and fixing is the whole point.

**Fresh audit agents each round.** Don't reuse auditors — carried context biases toward "already checked" areas.

### Audit Triage

After collecting findings from all auditors:

**Refactor gate:** For any finding categorized as "refactor" (not a bug or security issue), apply this bar: *"Would a senior engineer say this is clearly wrong, not just imperfect?"* Reject style preferences and marginal improvements.

**Severity routing:**
- **Critical/High** — implementer fixes immediately, re-audit
- **Medium** — include in next fix round
- **Low/Cosmetic** — fix inline if trivial, otherwise note in completion summary and skip

**Budget check:** If fix rounds add 30%+ to the original implementation diff, tighten scope — skip medium/low simplify findings, focus on harden patches and spec gaps.

**Drift check (between audit rounds):** Before spawning the next audit round, re-read the original task description. If findings are pulling into unrelated areas or scope has expanded beyond the task, re-scope or exit the audit loop.

### Audit Loop Exit

Exit when ANY are true:
1. **Clean audit** — all auditors report zero findings
2. **Low-only round** — all remaining findings are low severity, fix inline
3. **Loop cap reached** — 3 audit rounds completed. Fix remaining critical/high inline, log unresolved medium/low in completion summary

### Implementer Status Protocol

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

### When Tasks Fail: Debugging Protocol

When a task fails during execution (test failures, unexpected behavior, build errors), follow the debugging protocol in `debugging-protocol.md`:

1. **Investigate** — read errors completely, reproduce, check recent changes, trace data flow
2. **Analyze** — find working examples, compare against references, identify differences
3. **Hypothesize** — simple bugs: sequential single hypothesis. Complex bugs with multiple plausible causes: dispatch parallel debug team (one Explore agent per hypothesis)
4. **Implement** — create failing test, fix root cause, verify

**Iron law: no fixes without root cause investigation.** If 3+ fix attempts fail, question the architecture and escalate to user.

### Verification Gates

At every phase transition and before any completion claim, follow the verification protocol in `verification-protocol.md`:

1. **IDENTIFY** what command proves the claim
2. **RUN** the full command (fresh, in this message)
3. **READ** full output, check exit code
4. **VERIFY** output confirms the claim
5. **ONLY THEN** make the claim

No "should pass," no "looks correct," no trusting agent team reports without independent verification.

---

## Phase 6: Completion

After all tasks are executed and verified:

1. **Run full test suite** — verify everything passes (fresh output required)
2. **Run linter** — verify clean output
3. **Determine base branch:**
   ```bash
   git merge-base HEAD main 2>/dev/null || git merge-base HEAD master 2>/dev/null
   ```

4. **Present options:**

```
Implementation complete. All tests pass. What would you like to do?

1. Merge back to <base-branch> locally
2. Push and create a Pull Request
3. Keep the branch as-is (I'll handle it later)
4. Discard this work

Which option?
```

5. **Execute choice:**
   - **Merge locally:** checkout base -> pull -> merge -> verify tests on merged result -> delete feature branch -> cleanup worktree if applicable
   - **Push and create PR:** push -> create PR with summary and test plan
   - **Keep as-is:** report branch name and worktree path, done
   - **Discard:** require user to type "discard" to confirm -> delete branch -> cleanup worktree

**Never** proceed with failing tests, merge without verifying, delete work without confirmation, or dismiss pre-existing test failures as "not our problem."

### Learning Loop (completion summary)

After all tasks, produce a summary that includes audit findings across all rounds:

```
## Completion Summary

**Audit rounds:** N of 3 max
**Exit reason:** clean audit | low-only round | loop cap

### Recurring patterns
- [pattern]: appeared N times across rounds, severity, resolution
- [pattern]: ...

### Unresolved (low severity, deferred)
- [finding]: reason deferred

### Out-of-scope observations
- [anything auditors flagged outside the task scope]
```

Recurring patterns are the signal — if the same finding type appears across multiple tasks or rounds, it indicates a systemic issue worth noting for future work.

---

## TDD Protocol

All implementation follows test-driven development:

1. **RED** — write one failing test showing desired behavior
2. **Verify RED** — run test, confirm it fails for the right reason (feature missing, not typo)
3. **GREEN** — write minimal code to pass the test
4. **Verify GREEN** — run test, confirm it passes, no other tests broken
5. **REFACTOR** — clean up, keep tests green
6. **Repeat**

**If code is written before a test:** delete it, start over with the test. No exceptions without user permission.

---

## Skill Taxonomy Maintenance

coding-team reads `~/.claude/skills/skill-taxonomy.yml` to map skills to workers.

- **Installing a skill:** Add it to the appropriate category. If no category fits, create a new one with role mappings.
- **Removing a skill:** Remove its entry from the taxonomy.
- **The taxonomy is advisory** — workers decide which skills to actually invoke based on the task.

---

## Handling Review Feedback

When receiving code review feedback (from user, PR reviewers, or quality reviewer agents), follow `review-reception-protocol.md`:

- Verify before implementing — don't blindly agree
- Push back with technical reasoning when feedback is wrong
- Ask for clarification on unclear items before implementing any
- No performative agreement ("Great point!") — just fix it or discuss technically
- One item at a time, test each

---

## Parallel Dispatch

When facing multiple independent failures or tasks, follow `parallel-dispatch-protocol.md`:

- Group failures by independent domain
- One agent team per domain, all dispatched in same message
- Each team gets focused scope, clear context, constraints, and expected output
- Review all results, check for conflicts, run full test suite

---

## Output Files

- `docs/plans/YYYY-MM-DD-<feature>-design.md` — design doc (written after Phase 3 approval)
- `docs/plans/YYYY-MM-DD-<feature>.md` — implementation plan (written after Phase 4)

---

## Reference Files

All protocol files live in the coding-team skill directory:

| File | Purpose |
|------|---------|
| `prompts/implementer.md` | Implementer (task team member) prompt template |
| `prompts/spec-reviewer.md` | Spec compliance + TDD verification (read-only) |
| `prompts/simplify-auditor.md` | Simplify auditor — clarity and complexity (read-only) |
| `prompts/harden-auditor.md` | Harden auditor — security and resilience (read-only) |
| `prompts/quality-reviewer.md` | Legacy quality reviewer (use simplify + harden instead) |
| `prompts/spec-doc-reviewer.md` | Design doc reviewer template |
| `prompts/plan-doc-reviewer.md` | Plan doc reviewer template |
| `debugging-protocol.md` | Four-phase root cause investigation |
| `verification-protocol.md` | Evidence-before-claims gates |
| `worktree-protocol.md` | Git worktree setup and cleanup |
| `review-reception-protocol.md` | How to handle review feedback |
| `parallel-dispatch-protocol.md` | When/how to dispatch parallel agent teams |

---

## Red Flags

**Never:**
- Start implementation on main/master without explicit user consent
- Skip reviews (spec compliance OR code quality)
- Proceed with unfixed review issues
- Dispatch multiple task teams in parallel on same files (conflicts)
- Make implementer read plan file (provide full text)
- Trust agent team reports without independent verification
- Claim work is done without running tests in this message
- Fix bugs without root cause investigation
- Retry the same failed approach more than 3 times
- Performatively agree with review feedback without verifying
- Dismiss pre-existing test failures — fix them or escalate, never ignore

**Always:**
- Verify tests before offering completion options
- Present exactly 4 structured completion options
- Get confirmation before discarding work
- Use the model tier assigned in the plan
- Match process weight to task weight — don't force full pipeline for trivial tasks
