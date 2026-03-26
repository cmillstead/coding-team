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

**Step 0: Detect available coordination tools.**

```
AGENT_TEAMS_AVAILABLE = false

Check if Teammate tool is available in this session.
Check if SendMessage tool is available in this session.
Check if TaskCreate (team-aware variant) is available.

If ALL three are present:
  AGENT_TEAMS_AVAILABLE = true
```

`AGENT_TEAMS_AVAILABLE` gates **capability** — whether agent teams tools exist. Task characteristics gate **preference** — whether to use them. At every multi-agent dispatch point, evaluate:

```
1. COORDINATION: Will agents need to talk to each other during execution?
   - Shared files/state between agents → yes
   - One agent's findings could change another's approach → yes
   - Agents working on provably independent scope → no

2. DISCOVERY: Is the task decomposition known upfront?
   - Clear, independent pieces already defined → no
   - Agents may discover unexpected dependencies → yes

3. COMPLEXITY: Does the work require judgment or just execution?
   - Mechanical changes with complete spec → no
   - Design decisions, architectural trade-offs → yes

If COORDINATION = yes AND AGENT_TEAMS_AVAILABLE = true → agent teams
If COORDINATION = no → subagents regardless of AGENT_TEAMS_AVAILABLE
```

**COORDINATION is the dominant signal.** Simplified: will one agent's work affect another agent's work in real time? Yes → agent teams. No → subagents.

**Note:** The `Task` tool (subagent spawner) and the `TaskCreate`/`TaskList`/`TaskUpdate` tools (team task management) are different tools. Agent teams require both — `Task` for spawning agents into teams, and `TaskCreate`/`TaskList` for the shared task list. If only `Task` is available, `AGENT_TEAMS_AVAILABLE` remains false.

**Step 1: Check if this is a continuation.** If the user mentions a phase number, task number, feature name, "continue", "pick up where I left off", or any reference to prior work — read `phases/session-resume.md` and follow its instructions. Then proceed to Step 3.

**Step 2: Fresh task.** If no continuation signals detected, proceed directly to Step 3.

**Step 3: Route.** For fresh tasks (no prior plans), or after plan discovery:

| User's situation | Entry point |
|---|---|
| Task modifies CC instruction files (`phases/*.md`, `agents/*.md`, `prompts/*.md`, `skills/*/SKILL.md`, `SKILL.md`, `CLAUDE.md`, `memory/*.md`) AND user has no spec or a vague request | **Phase 2** — route through design team with Prompt/Skill Specialist |
| Task modifies CC instruction files AND user has a complete spec with explicit file paths and content | **Phase 4** with PROMPT_CRAFT_ADVISORY on every task that touches instruction files |
| CC behavioral issue ("CC keeps doing X", "CC ignores my instructions", "CC uses wrong tool") | `/prompt-craft diagnose` skill — not `/debug`. Behavioral issues are instruction problems, not code bugs. |
| New feature idea, vague request | **Phase 1** — start dialogue |
| Has a design/spec, needs a plan | **Phase 4** — planning worker |
| Has a plan file, ready to build | **Phase 5** — execution |
| Bug report or test failure | `/debug` skill (`skills/debug/SKILL.md`) |
| Existing PR with review feedback | `/review-feedback` skill (`skills/review-feedback/SKILL.md`) |
| Multiple independent failures | `/parallel-fix` skill (`skills/parallel-fix/SKILL.md`) |
| Single-file change under 20 lines with a complete spec | Phase 5 with a single haiku-tier task. Still goes through the pipeline. |
| User says "autoplan", "auto-review", "run all reviews", or "make the decisions" | **Phase 4 auto-advance** — run Phase 1→4 sequentially, auto-deciding intermediate questions using these principles: (1) completeness over shortcuts, (2) pragmatic over theoretical, (3) explicit over clever, (4) bias toward action, (5) DRY, (6) boil lakes not oceans. Surface only taste decisions (close approaches, borderline scope) at a final approval gate before Phase 5. |

---

## Guiding Principles

These apply to every agent in the team:

- **Scrap, don't fix** — if a worker's output is thin, off-scope, or clearly low quality, the Team Leader respawns it rather than patching around it. Bad agent output is an engineering problem, not a starting point.
- **Never mock what you can use for real** — tests must use real implementations wherever available. Only mock external systems that are genuinely unavailable in the test environment (remote APIs, third-party services). Never mock the thing being tested.
- **Quality gates before handoff** — no agent passes work to the next stage until tests pass and linting is clean. Build green -> commit -> move on.
- **Focused agents produce correct agents** — one worker, one lens, one scope. Workers that wander produce slop.
- **No ambiguity in specs** — the Planning Worker leaves nothing to inference. Exact file paths, exact line ranges, complete code snippets, exact commands with expected output.
- **Evidence before claims** — no completion claims without fresh verification output. If you haven't run the command in this message, you cannot claim it passes. See `/verify` skill (`skills/verify/SKILL.md`).
- **Right-size the model** — use the cheapest model that can handle the task. Haiku for mechanical edits, Sonnet for implementation, Opus for architecture and review.
- **Dispatch first, self-execute second** — when you have both delegatable work (agent tasks) and self-executable work (memory saves, doc writes, context reads), dispatch agents FIRST, then do your own tasks while agents run. Agent work takes longer; starting it immediately maximizes parallelism. Never block agent dispatch behind your own lightweight tasks.

---

## Phase Sequence

Each phase reads its detail file on entry. Do not read ahead — load only the active phase.

### Phase 1: Dialogue
**Purpose:** Clarify requirements, propose approaches, get user approval.
**Input:** User's request + project context (CLAUDE.md, recent commits, files).
**Output:** Approved approach with trade-offs.
**Detail:** Read `phases/dialogue.md`
**Exit gate:** User has approved an approach. Do NOT proceed without approval.

### Phase 2: Design Team
**Purpose:** Specialist workers analyze the problem from multiple angles.
**Input:** Approved approach from Phase 1 + project context.
**Output:** Synthesized design doc.
**Detail:** Read `phases/design-team.md`
**Exit gate:** User has approved the design doc.

### Phase 3: Spec Review
**Purpose:** Write and validate the design spec.
**Input:** Approved design doc from Phase 2.
**Output:** Reviewed spec at `docs/plans/YYYY-MM-DD-<feature>-design.md`.
**Detail:** Read `phases/spec-review.md`
**Exit gate:** User has confirmed the written spec.

### Phase 4: Planning
**Purpose:** Produce detailed implementation plan with TDD tasks.
**Input:** Approved spec from Phase 3 + project context.
**Output:** Reviewed plan at `docs/plans/YYYY-MM-DD-<feature>.md`.
**Detail:** Read `phases/planning.md`
**Exit gate:** Plan passes automated review.

### Phase 5: Execution
**Purpose:** Task-by-task implementation with audit loops.
**Input:** Approved plan from Phase 4.
**Output:** Implemented, tested, audited code on feature branch.
**Detail:** Read `phases/execution.md`
**Exit gate:** All tasks pass verification with fresh test output.

### Phase 6: Completion
**Purpose:** Verify, merge/PR/keep/discard, learning loop.
**Input:** Completed execution from Phase 5.
**Output:** Merged code or PR or kept branch + completion summary.
**Detail:** Read `phases/completion.md`
**Exit gate:** User has chosen a completion option and it's been executed.

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
- Dismiss pre-existing failures or findings — fix them or escalate, never ignore. "Pre-existing" and "not a regression" are NOT valid reasons to skip. A bug is a bug regardless of when it was introduced.
- Silently drop findings — every scan finding, review comment, or enumerated issue must be planned (fix, defer with rationale, or false positive) and every planned task must be executed
- Write code directly during Phase 5 — the main agent is the orchestrator, not the implementer. Use Edit/Write only in Phases 1-4 (plans, specs). During execution, spawn teammates (or subagents if agent teams unavailable) for all code changes.
- Suggest `/ship` (gstack) for deploying or creating PRs — always suggest `/release` (`skills/release/SKILL.md`) instead. Similarly, suggest `/retrospective` not `/retro`, and `/doc-sync` not `/document-release`. Coding-team has its own equivalents for these gstack skills.

**Always:**
- Verify tests before offering completion options
- Present exactly 4 structured completion options
- Get confirmation before discarding work
- Use the model tier assigned in the plan
- Match process weight to task weight

---

## Output Files

- `docs/plans/YYYY-MM-DD-<feature>-design.md` — design doc (written after Phase 3 approval)
- `docs/plans/YYYY-MM-DD-<feature>.md` — implementation plan (written after Phase 4)

---

## Reference Files

**Standalone skills** (can be invoked independently or from the pipeline):

| Skill | Path | Purpose |
|-------|------|---------|
| `/debug` | `skills/debug/SKILL.md` | Four-phase root cause investigation |
| `/verify` | `skills/verify/SKILL.md` | Evidence-before-claims gates |
| `/review-feedback` | `skills/review-feedback/SKILL.md` | How to handle review feedback |
| `/worktree` | `skills/worktree/SKILL.md` | Git worktree setup and cleanup |
| `/parallel-fix` | `skills/parallel-fix/SKILL.md` | Parallel agent dispatch for independent failures |
| `/tdd` | `skills/tdd/SKILL.md` | Test-driven development cycle |
| `/prompt-craft` | `skills/prompt-craft/SKILL.md` | Skill & prompt engineering, diagnosis, audit. For instruction text quality — not harness infrastructure. |
| `/harness-engineer` | `skills/harness-engineer/SKILL.md` | Harness infrastructure: hooks, rules, settings, constraint promotion, maturity assessment. For systems design — not instruction text. |
| `/second-opinion` | `skills/second-opinion/SKILL.md` | Cross-model second opinion via OpenAI Codex CLI |
| `/scope-lock` | `skills/scope-lock/SKILL.md` | Restrict edits to a directory during debugging |
| `/scope-unlock` | `skills/scope-unlock/SKILL.md` | Remove scope-lock edit restriction |
| `/release` | `skills/release/SKILL.md` | Automated release: sync, test, push, PR |
| `/retrospective` | `skills/retrospective/SKILL.md` | Post-ship engineering retrospective. **Always use this, not gstack's `/retro`.** |
| `/doc-sync` | `skills/doc-sync/SKILL.md` | Post-ship documentation update |

**Phase details** (loaded on demand by the active phase):

| Phase | File |
|-------|------|
| Session Resume | `phases/session-resume.md` |
| Dialogue | `phases/dialogue.md` |
| Design Team | `phases/design-team.md` |
| Spec Review | `phases/spec-review.md` |
| Planning | `phases/planning.md` |
| Execution | `phases/execution.md` |
| Post-Execution Review | `phases/post-execution-review.md` |
| Completion | `phases/completion.md` |

**Extracted on-demand files** (loaded by phase files when needed):

| File | Extracted from | Purpose |
|------|---------------|---------|
| `phases/audit-loop.md` | execution.md | Audit team dispatch, triage, and loop exit |
| `phases/design-team-lifecycle.md` | design-team.md | Agent teams lifecycle details |
| `phases/doc-drift-scan.md` | execution.md | Documentation drift scan |
| `phases/memory-nudge.md` | completion.md | Session learning extraction |
| `phases/plan-format.md` | planning.md | Plan document template and task structure |
| `phases/planning-next-steps.md` | planning.md | Risk signals and second-opinion gate |

**Agent definitions** (used by the execution loop):

| File | Purpose |
|------|---------|
| `agents/ct-implementer.md` | Implementer (task team member) prompt template |
| `agents/ct-spec-reviewer.md` | Spec compliance + TDD verification (read-only) |
| `agents/ct-simplify-auditor.md` | Simplify auditor — clarity and complexity (read-only) |
| `agents/ct-harden-auditor.md` | Harden auditor — security and resilience (read-only) |
| `agents/ct-prompt-craft-auditor.md` | Prompt-craft auditor — CC instruction quality (read-only, conditional) |
| `agents/ct-harness-engineer.md` | Harness engineer — hooks, rules, settings, constraint promotion, maturity (read-write for audit commands) |
| `agents/ct-spec-doc-reviewer.md` | Design doc reviewer template |
| `agents/ct-plan-doc-reviewer.md` | Plan doc reviewer template |
