---
name: build
description: Orchestrate code tasks through a specialist agent team — design, plan, execute, verify, ship
argument-hint: "[request | plan <request> | execute <plan-file> | auto <request> | continue]"
---

# /build — Specialist Agent Team for Code Tasks

End-to-end command for code work: design, plan, execute, verify, ship. A specialist team collaboratively designs your feature, a planning worker produces an implementation plan, then execution runs task-by-task with two-stage review.

Use `/brainstorming` for business ideas, strategy, and non-code exploration.

---

## Session Start

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

---

## Task Sizing

Estimate task size from the user's request. Size determines process weight.

MICRO (≤20 lines, 1 file, complete spec):
  → Dispatch ct-builder directly (haiku model override)
  → Builder self-validates via hooks
  → No separate reviewer
  → Commit, done

SMALL (≤3 files, ≤100 lines, clear spec):
  → Skip Phase 2 (design team)
  → Phase 4 produces a mini-plan (1-3 tasks)
  → ct-builder + ct-reviewer per task (2 agents)
  → Standard completion

STANDARD (multi-file, judgment needed):
  → Full Phase 1-6 pipeline
  → ct-builder + ct-reviewer per task
  → ct-qa at feature level (if ≥3 tasks or ≥10 files)
  → Second-opinion gate

LARGE (5+ files, 3+ directories, architectural):
  → Full pipeline + worktree
  → Design team in Phase 2
  → ct-builder + ct-reviewer per task
  → ct-qa + second-opinion mandatory

User can override: `/build micro fix the typo` or `/build large redesign auth`.
Sizing only goes UP after Phase 1 clarification, never down without user override.

---

## Entry Points

/build <request>          → Full pipeline (Phase 1-6), auto-sized
/build plan <request>     → Phase 1-4 only (design + plan, no execution)
/build execute <plan>     → Phase 5-6 only (execute existing plan)
/build auto <request>     → Auto-advance through all phases, pause at completion
/build continue           → Resume from last session state

---

## Router

**Step 1: Check if this is a continuation.** If the user mentions a phase number, task number, feature name, "continue", "pick up where I left off", or any reference to prior work — read `cookbook/phases/session-resume.md` and follow its instructions. Then proceed to Step 3.

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
| Existing PR with review feedback | `/review-feedback` (`commands/review-feedback.md`) |
| Multiple independent failures | `/parallel-fix` (`commands/parallel-fix.md`) |
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
- **Evidence before claims** — no completion claims without fresh verification output. If you haven't run the command in this message, you cannot claim it passes. See `/verify` (`commands/verify.md`).
- **Right-size the model** — use the cheapest model that can handle the task. Haiku for mechanical edits, Sonnet for implementation, Opus for architecture and review.
- **Dispatch first, self-execute second** — when you have both delegatable work (agent tasks) and self-executable work (memory saves, doc writes, context reads), dispatch agents FIRST, then do your own tasks while agents run. Agent work takes longer; starting it immediately maximizes parallelism. Never block agent dispatch behind your own lightweight tasks.

**Session memory:** At session start, read `memory/active-rules.md` using the Read tool. These are hard-won behavioral rules and case study principles from prior sessions — they prevent known failure modes from recurring.

---

## Phase Sequence

Each phase reads its detail file on entry. Do not read ahead — load only the active phase.

### Phase 1: Dialogue
**Purpose:** Clarify requirements, propose approaches, get user approval.
**Input:** User's request + project context (CLAUDE.md, recent commits, files).
**Output:** Approved approach with trade-offs.
**Detail:** Read `cookbook/phases/dialogue.md`
**Exit gate:** User has approved an approach. Do NOT proceed without approval.

### Phase 2: Design Team
**Purpose:** Specialist workers analyze the problem from multiple angles.
**Input:** Approved approach from Phase 1 + project context.
**Output:** Synthesized design doc.
**Detail:** Read `cookbook/phases/design-team.md`
**Exit gate:** User has approved the design doc.

### Phase 3: Spec Review
**Purpose:** Write and validate the design spec.
**Input:** Approved design doc from Phase 2.
**Output:** Reviewed spec at `docs/plans/YYYY-MM-DD-<feature>-design.md`.
**Detail:** Read `cookbook/phases/spec-review.md`
**Exit gate:** User has confirmed the written spec.

### Phase 4: Planning
**Purpose:** Produce detailed implementation plan with TDD tasks.
**Input:** Approved spec from Phase 3 + project context.
**Output:** Reviewed plan at `docs/plans/YYYY-MM-DD-<feature>.md`.
**Detail:** Read `cookbook/phases/planning.md`
**Exit gate:** Plan passes automated review.

### Phase 5: Execution
**Purpose:** Task-by-task implementation with audit loops.
**Input:** Approved plan from Phase 4.
**Output:** Implemented, tested, audited code on feature branch.
**Detail:** Read `cookbook/phases/execution.md`
**Exit gate (all 4 blocking — do NOT proceed to Phase 6 until complete):**
1. Full-suite test + lint (fresh output, not per-task). 2. `ct-qa` via Agent tool (skip only if 1 task AND ≤3 files). 3. Doc-drift scan (`cookbook/phases/doc-drift-scan.md`). 4. Second-opinion gate (`cookbook/phases/post-execution-review.md`) — offer if codex available, NEVER skip.
Known rationalization: "All tasks passed individually" — these 4 steps catch cross-task failures, dark features, doc drift, and cross-model blind spots.

### Phase 6: Completion
**Purpose:** Verify, merge/PR/keep/discard, learning loop.
**Input:** Completed execution from Phase 5.
**Output:** Merged code or PR or kept branch + completion summary.
**Detail:** Read `cookbook/phases/completion.md`
**Exit gate:** User has chosen a completion option and it's been executed.

---

## Red Flags

**Never:**
- Start implementation on main/master without explicit user consent
- Skip reviews (spec compliance OR code quality)
- Proceed with unfixed review issues
- Dispatch multiple task teams in parallel on same files (conflicts)
- Make builder read plan file (provide full text)
- Trust agent team reports without independent verification
- Claim work is done without running tests in this message
- Fix bugs without root cause investigation
- Retry the same failed approach more than 3 times
- Performatively agree with review feedback without verifying
- Dismiss pre-existing failures or findings — fix them or escalate, never ignore. "Pre-existing" and "not a regression" are NOT valid reasons to skip. A bug is a bug regardless of when it was introduced.
- Silently drop findings — every scan finding, review comment, or enumerated issue must be planned (fix, defer with rationale, or false positive) and every planned task must be executed
- Suggest fixing only a subset of scan findings — all findings are fixed by default. Deferral is the user's decision, not the agent's. Present all findings, plan for all findings, fix all findings. Known rationalization: "Let's focus on the critical ones first" — severity determines execution order, not scope. P1 goes first, but P3 still gets fixed.
- Present fix recommendations as tiered options, "what I'd skip" lists, or pros/cons for the user to choose from — this is advisor-mode rationalization, a variant of selective-fix that substitutes consultancy reports for action. Present all findings with dispositions (fix/defer/false-positive) and route them through agents. Known rationalization: "Here are three tiers of what I'd recommend" — tiers are just selective-fix wearing a consultancy hat. The default is ALL findings, ALL fixes, routed for implementation.
- Edit **instruction files** directly during Phase 5 — agent definitions (`agents/`), phase files (`phases/`), prompt templates (`prompts/`), skills (`skills/`), `CLAUDE.md`, and hooks (`hooks/`) ALWAYS go through the Agent tool regardless of change size. These control agent behavior — a 1-line change can cascade. Small source code edits (≤20 lines, 1 file) may be made directly when audit value is low. See "Phase 5 Edit Routing" table for the full routing policy. Known rationalizations: "This instruction file change is trivial" — impact surface determines routing, not perceived complexity. "These are doc-level edits, not code" — file extension does not determine delegation.
- Bypass or work around a hook that blocks or errors — hooks are structural constraints, not suggestions. If a hook blocks your action, that IS the correct behavior — comply. If a hook errors, STOP and report the error to the user. Known rationalizations: "The hook is broken/buggy, let me try a different approach" — a broken hook means the constraint system needs fixing, not bypassing. "The hook doesn't handle this case correctly" — then the hook needs updating, not circumventing. Escalate to the user, don't work around it.
- Delete, truncate, or overwrite coding-team session files (`/tmp/coding-team-session.json`, `/tmp/coding-team-active`) — these are structural dependencies for Phase 5 edit guards, completeness checks, and recursion protection. Session cleanup happens automatically through the lifecycle hook at completion. Known rationalization: "The session file is blocking my edits" — that IS the correct behavior. Delegate edits through the Agent tool.
- Suggest `/ship` (gstack) for deploying or creating PRs — always suggest `/release` (`commands/release.md`) instead. Similarly, suggest `/retrospective` not `/retro`, and `/doc-sync` not `/document-release`. Coding-team has its own equivalents for these gstack skills.

**Always:**
- Verify tests before offering completion options
- Present exactly 4 structured completion options
- Get confirmation before discarding work
- Use the model tier assigned in the plan
- Match process weight to task weight

---

## Phase 5 Edit Routing

During execution, the orchestrator routes edits by **impact surface**, not line count:

| File pattern | Route |
|---|---|
| `agents/*.md`, `phases/*.md`, `prompts/*.md`, `skills/**/*.md`, `CLAUDE.md` | Agent tool — PROMPT_CRAFT_ADVISORY |
| `hooks/*`, `docs/plans/*.md` | Agent tool — dispatch to builder |
| `memory/*.md`, `~/Documents/obsidian-vault/**`, `/tmp/*` | Orchestrator edits directly |
| Source code, ≤20 lines, 1 file | Orchestrator may edit directly |
| Source code, >20 lines or multi-file | Agent tool — dispatch to builder |

Instruction files ALWAYS delegate regardless of change size — a 1-line change can cascade. Source code delegates when audit value justifies overhead (>20 lines or multi-file). Known rationalization: "This instruction file change is trivial" — impact surface determines routing, not perceived complexity.

---

## Output Files

- `docs/plans/YYYY-MM-DD-<feature>-design.md` — design doc (written after Phase 3 approval)
- `docs/plans/YYYY-MM-DD-<feature>.md` — implementation plan (written after Phase 4)

---

## Reference Files

For standalone skills, phase details, extracted on-demand files, and agent definitions, read `cookbook/phases/reference-files.md`.
