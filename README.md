# coding-team

Self-contained agent team skill for [Claude Code](https://claude.com/claude-code). Design, plan, execute, verify, and ship code — end to end.

## What it does

Assembles specialist agent teams to collaboratively work through code tasks. The skill routes your request to the right phase, assembles the right team, picks the right coordination mode, and manages the full lifecycle:

1. **Dialogue** — clarify requirements, explore approaches, get alignment
2. **Design team** — specialist workers analyze the problem from multiple angles
3. **Spec review** — automated reviewer validates the design doc
4. **Planning** — detailed TDD implementation plan with model routing per task
5. **Execution** — task teams (implementer + audit team) build and verify
6. **Completion** — full verification, learning loop, then merge / PR / keep / discard

Each phase loads on demand — the main SKILL.md is a ~300 line router. Standalone skills can be invoked independently outside the pipeline.

## Architecture

### Composable phases

The main SKILL.md is a router that knows the phase sequence, input/output contracts, and which file to read for details. Phase files load on demand. Standalone skills load independently.

**Context window budget:**

| Invocation | Loaded | Lines |
|---|---|---|
| `/coding-team` (router decides) | Main SKILL.md | ~302 |
| `/coding-team` → Phase 4 (planning) | Main + `phases/planning.md` | ~584 |
| `/coding-team` → Phase 5 (execution) | Main + `phases/execution.md` | ~607 |
| `/coding-team` → Phase 2 (design) | Main + `phases/design-team.md` | ~533 |
| `/coding-team` → Phase 6 (completion) | Main + `phases/completion.md` | ~531 |
| `/debug` (standalone) | `skills/debug/SKILL.md` only | ~168 |
| `/verify` (standalone) | `skills/verify/SKILL.md` only | ~55 |
| `/prompt-craft` (standalone) | `skills/prompt-craft/SKILL.md` only | ~263 |

Phase files do not reference each other. The main SKILL.md's phase contracts define the input/output handoff between phases.

### Agent teams vs subagents

The skill uses two coordination modes and picks between them at every dispatch point using a three-signal heuristic:

**Agent teams** (native Claude Code agent teams with `Teammate`, `SendMessage`, shared task list) — used when agents need to coordinate in real time. Requires `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`, v2.1.32+, Opus 4.6.

**Subagents** (Task/Agent tool, fire-and-forget) — used when work is pre-decomposed, independent, and agents just need to execute and report back.

The deciding question: **will one agent's work affect another agent's work in real time?** Yes → agent teams. No → subagents.

Three signals evaluated at each dispatch point:

| Signal | Yes → leans agent teams | No → leans subagents |
|---|---|---|
| **COORDINATION** — will agents need to talk? | Shared files/state, one agent's findings change another's approach | Provably independent scope, no overlap |
| **DISCOVERY** — is decomposition known upfront? | Unknown root cause, uncertain task boundaries | Pre-partitioned by user or plan |
| **COMPLEXITY** — does the work require judgment? | Design decisions, architectural trade-offs, ambiguous requirements | Mechanical changes, pattern-apply, copy-paste from spec |

COORDINATION is the dominant signal. If agents don't need to talk to each other, subagents are almost always right — even for complex tasks.

**Typical routing by phase:**

| Phase | Typical mode | Why |
|---|---|---|
| Design team (primary analysis) | Agent teams | Workers analyze unknown codebase from different angles, cross-domain concerns |
| Design team (cross-review) | Agent teams | Workers challenge each other's findings directly |
| Execution (implementer per task) | Subagents | Plan pre-decomposes into independent tasks with distinct files |
| Execution (audit team) | Subagents | Read-only reviewers report independently to lead |
| Debugging (3+ competing hypotheses) | Agent teams | Investigators disprove each other in real time |
| Parallel fix (independent domains) | Subagents | Pre-triaged, no coordination needed |
| Parallel fix (shared infrastructure) | Agent teams | Cross-domain discovery prevents conflicting fixes |

When agent teams aren't available, all patterns fall back to subagents.

### Model routing

Uses the cheapest model that can handle each task:

| Task type | Model | Examples |
|---|---|---|
| Mechanical | haiku | Single file edits, formatting, simple rewrites |
| Implementation | sonnet | Feature implementation, test writing, multi-file refactoring |
| Architecture/review | opus | Planning, design, spec review, complex debugging |

If a cheaper model fails or returns low-quality results, the task is re-dispatched with the next tier up.

## How it works

### Session routing

When invoked, the skill detects available coordination tools (agent teams vs subagents only), then checks whether you're continuing prior work. If you mention a phase, task number, feature name, or "continue" — it finds the **main repo root** (not a worktree), lists `docs/plans/*.md` to discover existing plans (never guesses filenames), reads headers to match your request, checks git log for progress, and for sessions idle 24+ hours checks what changed on main and surfaces a context refresh before resuming at the next incomplete task.

For fresh tasks (no prior plans), it routes based on what you bring:

| You have... | Entry point |
|---|---|
| Task modifying CC instruction files (phases, prompts, skills, CLAUDE.md) + vague request | Phase 2 with Prompt/Skill Specialist |
| Task modifying CC instruction files + complete spec | Phase 4 with prompt-craft advisory |
| CC behavioral issue ("CC keeps doing X", "CC ignores instructions") | `/prompt-craft diagnose` |
| A vague idea or new feature request | Phase 1 — dialogue to clarify |
| A design or spec, needs a plan | Phase 4 — planning worker |
| A plan file, ready to build | Phase 5 — execution |
| A bug report or test failure | `/debug` skill |
| A PR with review feedback | `/review-feedback` skill |
| Multiple independent failures | `/parallel-fix` skill |
| A trivial task (rename, typo, single-file fix) | Phase 5 with a single haiku-tier task |

### Phase 1: Dialogue

Reads project context, then asks clarifying questions one at a time — multiple choice preferred, open-ended when needed. For UI-related work, a visual companion is offered.

Proposes 2-3 approaches with trade-offs: at least one minimal viable approach (smallest diff), at least one ideal architecture approach (best long-term trajectory), and for complex features a dream state sketch (current → this plan → 12-month ideal). No work begins until you approve.

### Phase 2: Design team

Before spawning workers, the skill retrieves context from prior sessions: project-local `docs/team-memory.md` (codebase facts and known landmines) and relevant past episodes via QMD `vector_search` (pattern-matched, not keyword-matched). Both are passed as advisory context to all workers.

A Team Leader spawns specialist workers to analyze the problem. Workers run in parallel and are composed dynamically based on what the task needs.

**Specialist roles:**

| Role | Focus | Skip when |
|---|---|---|
| Architect | System design, composability, data flow | Trivial bug fixes |
| Senior Coder | Implementation approach, patterns, idiomatic code | Never |
| UX/UI Designer | First-run UX, error messages, discoverability | Pure backend / no user-facing surface |
| Tester | Test strategy, edge cases, coverage | Never |
| Security Engineer | Trust boundaries, input validation, threat model | Pure refactors with no new surface area |
| DevOps/Infra | CI/CD, deployment, observability | No deployment or infra changes |
| Data Engineer | Schema design, migrations, query performance | No data layer changes |
| Performance Engineer | Profiling, benchmarks, latency budgets | No performance-sensitive paths |
| Technical Writer | API docs, user guides, changelog | No public-facing or doc surface |
| Prompt/Skill Specialist | Prompt quality, skill coverage, instruction clarity | No prompt/skill changes in scope |

**Team sizing:**

| Complexity | Workers | Signals |
|---|---|---|
| Simple (1-2 files) | 2 | Isolated bug, single concern |
| Moderate (3-10 files) | 3-4 | Multi-file changes, 2-3 concerns |
| Complex (10-30 files) | 4-6 | Cross-cutting concerns, large features |
| Very complex (30+ files) | 6-9 | Full-stack features, systemic changes |

Workers produce findings from their specialist lens, then a cross-review pass lets workers flag cross-domain issues (via direct messaging with agent teams, or leader-mediated with subagents). The Team Leader synthesizes everything into a design doc.

If a worker's output is thin, off-scope, or low quality, the Team Leader respawns it with a tighter prompt rather than patching around bad output.

### Phase 3: Spec review

The design doc is written to `docs/plans/YYYY-MM-DD-<feature>-design.md` and passed through an automated spec reviewer that checks for completeness, consistency, clarity, scope, and YAGNI violations. Up to 3 review iterations before surfacing issues to you. You get a final review before proceeding.

### Phase 4: Planning

A Planning Worker (Architect + Senior Coder) produces a detailed implementation plan. Before writing tasks, it challenges scope: what existing code already solves sub-problems, what is the minimum set of changes, and if 8+ files or 2+ new classes are needed, can it be simpler?

**Plan structure:** header with goal/architecture/tech stack, context brief (environment, sacred paths, decision history, external dependencies, known landmines), optional project-specific eval criteria for auditors, file structure mapping, tasks with exact file paths, line ranges, complete code, exact commands with expected output. Each step is one action (2-5 minutes) with no ambiguity. Includes a failure modes table, NOT in scope section, what already exists section, and a traceability table when sourced from scan findings or review feedback — every input item mapped to fix, defer, or false positive. Nothing silently dropped.

The plan goes through an automated plan reviewer (up to 3 iterations) before being saved to `docs/plans/YYYY-MM-DD-<feature>.md`.

### Phase 5: Execution

The main agent is the **orchestrator** — it dispatches agents, reads results, and decides what to do next. It never writes code, edits files, or runs tests directly during this phase.

Before the first task, the full test suite runs to establish a **baseline**. Pre-existing failures are fixed before new work begins.

Each task gets a **task team**: an implementer (using TDD) plus an audit team of 3-4 read-only reviewers dispatched in parallel after the implementer reports done.

**Implementer** reports one of: DONE, DONE_WITH_CONCERNS, NEEDS_CONTEXT, or BLOCKED. Blocked tasks are assessed and escalated — never ignored or retried without changes.

**Audit team** (read-only, fresh agents each round):
- **Spec reviewer** — does the code match the spec? Was TDD followed? Flags possible doc drift.
- **Simplify auditor** — dead code, naming, over-abstraction. Only flags things "clearly wrong, not just imperfect."
- **Harden auditor** — input validation, injection vectors, auth, race conditions. Exploitable issues, not theoretical risks.
- **Prompt-craft auditor** (conditional) — only for tasks modifying CC instruction files. Checks framing, tool names, prohibitions, thresholds.

**Audit triage** applies a refactor gate ("would a senior engineer say this is clearly wrong?"), routes by severity, checks budget (30%+ diff growth → tighten scope), and checks for drift against the original task. The loop exits on clean audit, low-only findings, or 3-round cap.

**Completeness checks** run at two levels: per-task (every step accounted for before audit) and end-of-execution (every plan task has a commit before Phase 6).

**Documentation checks** run at three levels: per-task (implementer scans doc files before reporting DONE), end-of-execution (doc drift scan via sonnet agent against the full diff), and spec reviewer backstop (flags possible doc drift when implementer claims "no impact").

**Phase transition reminders** print after every exit gate — guiding you to the next phase, suggesting when to clear context, and recommending relevant skills (`/second-opinion`, `/prompt-craft`, `/scope-lock`). Mid-execution reminders fire every 3 tasks with progress and context check.

### Phase 6: Completion

Full test suite + linter verification, then four options: merge locally, push and create PR, keep branch as-is, or discard (requires typing "discard" to confirm). A learning loop summary captures recurring audit patterns, unresolved low-severity findings, and out-of-scope observations. A decision log prompt asks the user to record any architectural decisions made during the feature to `memory/decisions/`. A **Memory Nudge** then extracts session learnings: codebase facts → project-local `docs/team-memory.md` (with archive rotation), cross-project patterns → `memory/patterns.md`, and a structured episode → Obsidian vault (pattern-rich for vector_search retrieval in future Phase 2 sessions).

## Standalone skills

These can be invoked independently with their own slash commands, or used automatically by the pipeline:

| Skill | Command | Purpose | Lines |
|---|---|---|---|
| Debug | `/debug` | Four-phase root cause investigation. Parallel hypothesis teams for complex bugs. | ~168 |
| Verify | `/verify` | Evidence-before-claims gate. Run the command, read the output, then claim the result. | ~55 |
| TDD | `/tdd` | Red-green-refactor cycle with verification at each step. | ~31 |
| Review Feedback | `/review-feedback` | Technical evaluation of code review feedback. Push back when wrong. | ~91 |
| Worktree | `/worktree` | Isolated git worktree for feature work. | ~88 |
| Parallel Fix | `/parallel-fix` | Parallel agent dispatch for independent failures. | ~141 |
| Prompt Craft | `/prompt-craft` | Write, evaluate, and refine skills and agent prompts. Diagnose behavioral issues. | ~263 |
| Second Opinion | `/second-opinion` | Cross-model second opinion via OpenAI Codex CLI. Review, challenge, consult. | ~295 |
| Scope Lock | `/scope-lock` | Restrict edits to a directory during debugging. | ~48 |
| Scope Unlock | `/scope-unlock` | Remove scope-lock edit restriction. | ~26 |
| Release | `/release` | Automated release: sync base branch, test, push, create PR. | ~83 |
| Retrospective | `/retrospective` | Post-ship engineering retrospective with metrics. | ~65 |
| Doc Sync | `/doc-sync` | Post-ship documentation update — sync docs with shipped code. | ~70 |

## Internalized protocols

### TDD

All implementation follows test-driven development: RED (write failing test) → verify RED → GREEN (minimal code to pass) → verify GREEN → REFACTOR → repeat. If code is written before a test, delete it and start over.

### Verification

Evidence-before-claims at every phase transition: identify the command, run it fresh, read full output, verify it confirms the claim, only then make the claim. No "should pass." No trusting agent reports without independent verification.

### Debugging

Four-phase root cause investigation: investigate (read errors, reproduce, trace data flow), analyze (match against known patterns), hypothesize (single theory for simple bugs, parallel teams for complex), implement (failing test, single fix, verify). No fixes without root cause investigation. 3-strike escalation to user.

### Review reception

Technical evaluation, not performative agreement. Read, understand, verify against codebase, evaluate technically, then respond or push back with reasoning. No "Great point!" — just fix it or discuss technically.

## Guiding principles

- **Scrap, don't fix** — if a worker's output is thin or off-scope, respawn it rather than patching around it
- **Never mock what you can use for real** — only mock external systems genuinely unavailable in the test environment
- **Quality gates before handoff** — no agent passes work until tests pass and linting is clean
- **Focused agents produce correct agents** — one worker, one lens, one scope
- **No ambiguity in specs** — exact file paths, exact line ranges, complete code, exact commands
- **Evidence before claims** — no completion claims without fresh verification output
- **Right-size the model** — use the cheapest model that can handle the task
- **Right-size the coordination** — agent teams when agents need to talk, subagents when they don't

## Installation

Clone to your skills directory:

```bash
git clone git@github.com:cmillstead/coding-team.git ~/.claude/skills/coding-team
```

### Enable agent teams

Agent teams require an environment variable. Add to your shell profile:

```bash
# In ~/.zshrc or ~/.bashrc
export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
```

Or add to `~/.claude/settings.json`:

```json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```

Without this, all coordination falls back to subagents. The skill detects availability automatically at session start.

### Full pipeline only

If you only want the `/coding-team` orchestrated pipeline, you're done.

### Standalone skills (recommended)

Expose individual protocols as standalone slash commands:

```bash
# All standalone skills
for skill in debug verify review-feedback worktree parallel-fix tdd prompt-craft second-opinion scope-lock scope-unlock release retrospective doc-sync; do
  ln -s ~/.claude/skills/coding-team/skills/$skill ~/.claude/skills/$skill
done
```

Or pick just the ones you want:

```bash
# Just debugging and verification
ln -s ~/.claude/skills/coding-team/skills/debug ~/.claude/skills/debug
ln -s ~/.claude/skills/coding-team/skills/verify ~/.claude/skills/verify
```

### Optional: session-start hook

A lightweight `UserPromptSubmit` hook suggests `/coding-team` on the first message of each session for code tasks. It skips greetings, meta questions, and non-code requests.

```bash
cp coding-team-router.py ~/.claude/hooks/
```

Then add to `~/.claude/settings.json`:

```json
"UserPromptSubmit": [
  {
    "matcher": "",
    "hooks": [
      {
        "type": "command",
        "command": "python3 ~/.claude/hooks/coding-team-router.py"
      }
    ]
  }
]
```

### Skill taxonomy

coding-team reads `~/.claude/skills/skill-taxonomy.yml` to discover installed skills and route them to the right specialist workers during the design phase. Each worker gets an advisory block of relevant skills they can optionally invoke. Create a taxonomy file if you don't have one.

## Usage

```
/coding-team

Add caching to the API response layer with TTL-based invalidation
```

Or let the session-start hook suggest it automatically.

For simple tasks (typo, rename, single-file fix), the skill skips to Phase 5 with a single haiku-tier task.

## File structure

```
SKILL.md                          # router + phase contracts (~200 lines)
README.md                         # this file
coding-team-router.py             # session-start hook
memory/                           # behavioral feedback (persists across sessions)
  MEMORY.md                       #   index of feedback files
  feedback-*.md                   #   individual feedback entries
phases/                           # pipeline phase details (loaded on demand)
  dialogue.md                     #   Phase 1 — clarify, propose, approve
  design-team.md                  #   Phase 2 — specialist workers + synthesis
  spec-review.md                  #   Phase 3 — write and validate design spec
  planning.md                     #   Phase 4 — detailed TDD implementation plan
  execution.md                    #   Phase 5 — task teams + audit loops
  completion.md                   #   Phase 6 — verify, merge/PR, learning loop
skills/                           # standalone skills (can be invoked independently)
  debug/SKILL.md                  #   /debug — root cause investigation
  verify/SKILL.md                 #   /verify — evidence-before-claims gates
  review-feedback/SKILL.md        #   /review-feedback — handling review feedback
  worktree/SKILL.md               #   /worktree — git worktree setup/cleanup
  parallel-fix/SKILL.md           #   /parallel-fix — parallel agent dispatch
  tdd/SKILL.md                    #   /tdd — test-driven development cycle
  prompt-craft/SKILL.md           #   /prompt-craft — skill & prompt engineering
  second-opinion/SKILL.md         #   /second-opinion — cross-model second opinion
  scope-lock/SKILL.md             #   /scope-lock — restrict edits to a directory
  scope-unlock/SKILL.md           #   /scope-unlock — remove edit restriction
  release/SKILL.md                #   /release — automated release workflow
  retrospective/SKILL.md          #   /retrospective — engineering retrospective
  doc-sync/SKILL.md               #   /doc-sync — post-ship documentation update
prompts/                          # agent prompt templates (used by execution loop)
  implementer.md                  #   implementer agent template
  spec-reviewer.md                #   spec compliance + TDD verification (read-only)
  simplify-auditor.md             #   simplify auditor — clarity/complexity (read-only)
  harden-auditor.md               #   harden auditor — security/resilience (read-only)
  prompt-craft-auditor.md         #   prompt-craft auditor — CC instruction quality (read-only)
  quality-reviewer.md             #   legacy combined reviewer (use simplify + harden)
  spec-doc-reviewer.md            #   design doc reviewer
  plan-doc-reviewer.md            #   plan doc reviewer
```

## Output files

The skill writes two artifacts during execution:

- `docs/plans/YYYY-MM-DD-<feature>-design.md` — design doc (after Phase 3 approval)
- `docs/plans/YYYY-MM-DD-<feature>.md` — implementation plan (after Phase 4)

## Troubleshooting: Claude won't use coding-team

If the main agent keeps writing code directly instead of delegating to `/coding-team`, the problem is almost always **competing instructions in your CLAUDE.md**. The agent finds language that implies it should write code and uses that to rationalize skipping delegation.

Use `/prompt-craft diagnose` to find the conflict:

1. **Describe the symptom** — "the agent uses Edit directly instead of invoking /coding-team"
2. **prompt-craft traces the instruction** — finds the delegation rule and checks for competing signals
3. **It checks framing** — is the delegation rule the default path, or is it framed as an exception?
4. **It finds contradictions** — other lines in CLAUDE.md that assume the agent writes code

**Common culprits in CLAUDE.md:**

| Competing signal | Why it overrides delegation | Fix |
|---|---|---|
| "Write tests alongside new code" | Implies the agent writes tests | "Ensure tests exist (coding-team handles this)" |
| "Read code-style.md when writing Python" | Implies the agent writes Python | "Pass code-style.md to coding-team agents" |
| Model routing table without "(for coding-team agents)" | Reads as tasks for the main agent | Add "(for coding-team agents, NOT for you)" to the header |
| "Skip coding-team for simple tasks" | Agent reclassifies everything as "simple" | Remove the escape hatch entirely |
| Delegation rule buried mid-file | Gets outweighed by surrounding code-writing context | Move to line 1 of CLAUDE.md |

**Key insight:** A single "don't write code" rule loses to five other lines that implicitly assume you DO write code. Every line in CLAUDE.md must be consistent with the delegation model. `/prompt-craft diagnose` finds these inconsistencies.

## Credits

Incorporates ideas from:
- [superpowers](https://github.com/anthropics/claude-plugins-official) — TDD, verification gates, systematic debugging, worktrees, code review, plan execution
- [gstack](https://github.com/garrytan/gstack) — investigate, review, ship, and design review workflows
- [pskoett/agent-teams-simplify-and-harden](https://github.com/pskoett/pskoett-ai-skills) — split audit, refactor gate, drift check, learning loop
- [wshobson/team-composition-patterns](https://github.com/wshobson/agents) — team sizing heuristics, parallel debug teams
- [alinaqi/claude-bootstrap](https://github.com/alinaqi/claude-bootstrap) — independent TDD verification

## License

MIT
