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

The main SKILL.md (~200 lines) is a router that delegates to `commands/build.md` (~246 lines) as the primary orchestrator. Phase files in `cookbook/phases/` load on demand. Commands in `commands/` can be invoked as standalone slash commands.

## Architecture

### Composable phases

The SKILL.md is a router that knows the phase sequence, input/output contracts, and which file to read for details. `commands/build.md` is the main orchestrator that implements the full pipeline. Phase files load on demand. Commands can be invoked independently outside the pipeline.

**Context window budget:**

| Invocation | Loaded | Lines |
|---|---|---|
| `/coding-team` (router decides) | SKILL.md | ~200 |
| `/coding-team` → resume session | SKILL.md + `cookbook/phases/session-resume.md` | ~313 |
| `/coding-team` → Phase 1 (dialogue) | SKILL.md + `cookbook/phases/dialogue.md` | ~239 |
| `/coding-team` → Phase 2 (design) | SKILL.md + `cookbook/phases/design-team.md` | ~353 |
| `/coding-team` → Phase 4 (planning) | SKILL.md + `cookbook/phases/planning.md` | ~382 |
| `/coding-team` → Phase 5 (execution) | SKILL.md + `cookbook/phases/execution.md` | ~405 |
| `/coding-team` → Phase 5 post-exec | SKILL.md + execution + `cookbook/phases/post-execution-review.md` | ~481 |
| `/coding-team` → Phase 6 (completion) | SKILL.md + `cookbook/phases/completion.md` | ~361 |
| `/build` (command) | `commands/build.md` | ~246 |
| `/debug` (standalone) | `skills/debug/SKILL.md` only | ~200 |
| `/verify` (standalone) | `skills/verify/SKILL.md` only | ~55 |
| `/prompt-craft` (standalone) | `skills/prompt-craft/SKILL.md` only | ~152 |
| `/doc-write` (standalone) | `skills/doc-write/SKILL.md` only | ~189 |
| `/dep-audit` (standalone) | `skills/dep-audit/SKILL.md` only | ~108 |
| `/migration-guide` (standalone) | `skills/migration-guide/SKILL.md` only | ~127 |
| `/onboard` (standalone) | `skills/onboard/SKILL.md` only | ~101 |
| `/a11y` (standalone) | `skills/a11y/SKILL.md` only | ~106 |
| `/api-qa` (standalone) | `skills/api-qa/SKILL.md` only | ~93 |
| `/incident` (standalone) | `skills/incident/SKILL.md` only | ~129 |

Phase files do not reference each other. The SKILL.md's phase contracts define the input/output handoff between phases.

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
| Task modifying CC instruction files + vague request | Phase 2 with Prompt/Skill Specialist |
| Task modifying CC instruction files + complete spec | Phase 4 with prompt-craft advisory |
| CC behavioral issue ("CC keeps doing X", "CC ignores instructions") | `/prompt-craft diagnose` |
| A vague idea or new feature request | Phase 1 — dialogue to clarify |
| A design or spec, needs a plan | Phase 4 — planning worker |
| A plan file, ready to build | Phase 5 — execution |
| A bug report or test failure | `/debug` skill |
| A PR with review feedback | `/review-feedback` skill |
| Multiple independent failures | `/parallel-fix` skill |
| Single-file change under 20 lines with a complete spec | Phase 5 with a single haiku-tier task |

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

**Plan structure:** header with goal/architecture/tech stack, context brief (environment, sacred paths, decision history, external dependencies, known landmines), project-specific eval criteria for auditors (accumulated from `docs/project-evals.md` + context-derived), file structure mapping, tasks with exact file paths, line ranges, complete code, exact commands with expected output. Each step is one action (2-5 minutes) with no ambiguity. Includes a failure modes table, NOT in scope section, what already exists section, and a traceability table when sourced from scan findings or review feedback — every input item mapped to fix, defer, or false positive. Nothing silently dropped.

The plan goes through an automated plan reviewer (up to 3 iterations) before being saved to `docs/plans/YYYY-MM-DD-<feature>.md`.

### Phase 5: Execution

The main agent is the **orchestrator** — it dispatches agents, reads results, and decides what to do next. It never writes code, edits files, or runs tests directly during this phase.

Before the first task, the full test suite runs to establish a **baseline**. Pre-existing failures are fixed before new work begins.

Each task gets a **task team**: an implementer (using TDD) plus an audit team of 3-4 reviewers (spec and simplify are read-only; harden has Bash access for dependency audits) dispatched in parallel after the implementer reports done.

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

Full test suite + linter verification, then four options: merge locally, push and create PR (max 3 CI fix attempts, auto-cleanup on failure), keep branch as-is, or discard (requires typing "discard" to confirm). Completion summary persists to `docs/retros/` — either incorporated into the retrospective or saved standalone if the user skips `/retrospective`. A decision log prompt asks the user to record any architectural decisions made during the feature to `memory/decisions/`. A **Memory Nudge** then extracts session learnings: codebase facts → project-local `docs/team-memory.md` (with archive rotation), cross-project patterns → `memory/patterns.md`, and a structured episode → Obsidian vault (pattern-rich for vector_search retrieval in future Phase 2 sessions).

## Commands

Commands in `commands/` replace the old inline skill definitions. They can be invoked as standalone slash commands or used by the pipeline:

| Command | File | Purpose | Lines |
|---|---|---|---|
| `/build` | `commands/build.md` | Main orchestrator — full design/plan/execute/verify/ship pipeline | ~246 |
| `/verify` | `commands/verify.md` | Evidence-before-claims gate. Run the command, read the output, then claim the result. | ~55 |
| `/tdd` | `commands/tdd.md` | Red-green-refactor cycle with verification at each step. | ~31 |
| `/review-feedback` | `commands/review-feedback.md` | Technical evaluation of code review feedback. Push back when wrong. | ~90 |
| `/worktree` | `commands/worktree.md` | Isolated git worktree for feature work. | ~79 |
| `/parallel-fix` | `commands/parallel-fix.md` | Parallel agent dispatch for independent failures. | ~112 |
| `/second-opinion` | `commands/second-opinion.md` | Cross-model second opinion via OpenAI Codex CLI. | ~114 |
| `/scope-lock` | `commands/scope-lock.md` | Restrict edits to a directory during debugging. | ~43 |
| `/scope-unlock` | `commands/scope-unlock.md` | Remove scope-lock edit restriction. | ~20 |
| `/release` | `commands/release.md` | Automated release: sync base branch, test, push, create PR. | ~107 |
| `/retrospective` | `commands/retrospective.md` | Post-ship engineering retrospective. | ~87 |
| `/doc-sync` | `commands/doc-sync.md` | Post-ship documentation update — sync docs with shipped code. | ~64 |
| `/dep-audit` | `commands/dep-audit.md` | Dependency health, license, and upgrade audit. | ~108 |
| `/migration-guide` | `commands/migration-guide.md` | Breaking change upgrade guides. | ~121 |
| `/onboard` | `commands/onboard.md` | Guided codebase orientation. | ~102 |
| `/a11y` | `commands/a11y.md` | Accessibility audit — WCAG compliance, keyboard nav, ARIA. | ~107 |
| `/api-qa` | `commands/api-qa.md` | API contract testing — validation, error responses, breaking changes. | ~94 |
| `/incident` | `commands/incident.md` | Incident response — structured production incident coordination. | ~130 |

## Standalone skills

These are symlink targets in `skills/` that can be exposed as independent slash commands:

| Skill | Command | Purpose | Lines |
|---|---|---|---|
| Debug | `/debug` | Four-phase root cause investigation. Parallel hypothesis teams for complex bugs. | ~200 |
| Verify | `/verify` | Evidence-before-claims gate. | ~55 |
| TDD | `/tdd` | Red-green-refactor cycle with verification at each step. | ~31 |
| Review Feedback | `/review-feedback` | Technical evaluation of code review feedback. Push back when wrong. | ~91 |
| Worktree | `/worktree` | Isolated git worktree for feature work. | ~88 |
| Parallel Fix | `/parallel-fix` | Parallel agent dispatch for independent failures. | ~141 |
| Prompt Craft | `/prompt-craft` | Write, evaluate, and refine skills and agent prompts. Diagnose behavioral issues. | ~152 |
| Harness Engineer | `/harness-engineer` | Harness infrastructure design and audit: hooks, rules, settings, maturity. | ~87 |
| Second Opinion | `/second-opinion` | Cross-model second opinion via OpenAI Codex CLI. | ~115 |
| Scope Lock | `/scope-lock` | Restrict edits to a directory during debugging. | ~48 |
| Scope Unlock | `/scope-unlock` | Remove scope-lock edit restriction. | ~26 |
| Release | `/release` | Automated release: sync base branch, test, push, create PR. CI retry cap + orphan cleanup. | ~121 |
| Retrospective | `/retrospective` | Post-ship engineering retrospective. Saves to `docs/retros/`. | ~93 |
| Doc Sync | `/doc-sync` | Post-ship documentation update — sync docs with shipped code. | ~70 |
| Doc Write | `/doc-write` | Write docs from scratch or improve existing. | ~189 |
| Dep Audit | `/dep-audit` | Dependency health, license, and upgrade audit. | ~108 |
| Migration Guide | `/migration-guide` | Breaking change upgrade guides. | ~127 |
| Onboard | `/onboard` | Guided codebase orientation. | ~101 |
| A11y | `/a11y` | Accessibility audit — WCAG compliance, keyboard nav, ARIA. | ~106 |
| API QA | `/api-qa` | API contract testing — validation, error responses, breaking changes. | ~93 |
| Incident | `/incident` | Incident response — structured production incident coordination. | ~129 |

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
- **Dispatch first, self-execute second** — start long-running agent work before doing lightweight self-tasks

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

### Deploy hooks, agents, and config

The deploy script syncs hooks, agents, rules, and config from the repo to `~/.claude/`:

```bash
cd ~/.claude/skills/coding-team
bash scripts/deploy.sh
```

This deploys hooks to `~/.claude/hooks/`, agents to `~/.claude/agents/`, rules to `~/.claude/rules/`, and config to `~/.claude/`. Always run deploy BEFORE updating `settings.json` hook references.

### Full pipeline only

If you only want the `/coding-team` orchestrated pipeline, you're done after deploy.

### Standalone skills (recommended)

Expose individual protocols as standalone slash commands:

```bash
# All standalone skills
for skill in debug verify review-feedback worktree parallel-fix tdd prompt-craft harness-engineer second-opinion scope-lock scope-unlock release retrospective doc-sync doc-write dep-audit migration-guide onboard a11y api-qa incident; do
  ln -s ~/.claude/skills/coding-team/skills/$skill ~/.claude/skills/$skill
done
```

Or pick just the ones you want:

```bash
# Just debugging and verification
ln -s ~/.claude/skills/coding-team/skills/debug ~/.claude/skills/debug
ln -s ~/.claude/skills/coding-team/skills/verify ~/.claude/skills/verify
```

### Skill taxonomy

coding-team reads `~/.claude/skills/skill-taxonomy.yml` to discover installed skills and route them to the right specialist workers during the design phase. Each worker gets an advisory block of relevant skills they can optionally invoke. Create a taxonomy file if you don't have one.

## Usage

```
/coding-team

Add caching to the API response layer with TTL-based invalidation
```

Or invoke the build command directly:

```
/build Add caching to the API response layer with TTL-based invalidation
```

For simple tasks (typo, rename, single-file fix), the skill skips to Phase 5 with a single haiku-tier task.

## File structure

```
SKILL.md                          # router + phase contracts (~200 lines)
README.md                         # this file
commands/                         # slash commands (18 files, invokable independently)
  build.md                        #   /build — main orchestrator (~246 lines)
  verify.md                       #   /verify — evidence-before-claims
  tdd.md                          #   /tdd — red-green-refactor cycle
  review-feedback.md              #   /review-feedback — code review handling
  worktree.md                     #   /worktree — git worktree setup/cleanup
  parallel-fix.md                 #   /parallel-fix — parallel agent dispatch
  second-opinion.md               #   /second-opinion — cross-model review
  scope-lock.md                   #   /scope-lock — restrict edit directory
  scope-unlock.md                 #   /scope-unlock — remove edit restriction
  release.md                      #   /release — automated release workflow
  retrospective.md                #   /retrospective — post-ship retro
  doc-sync.md                     #   /doc-sync — post-ship doc update
  dep-audit.md                    #   /dep-audit — dependency audit
  migration-guide.md              #   /migration-guide — upgrade guides
  onboard.md                      #   /onboard — codebase orientation
  a11y.md                         #   /a11y — accessibility audit
  api-qa.md                       #   /api-qa — API contract testing
  incident.md                     #   /incident — incident response
cookbook/                          # on-demand phase details and references
  phases/                         #   pipeline phase files (loaded on demand)
    session-resume.md             #     continuation detection + plan discovery
    dialogue.md                   #     Phase 1 — clarify, propose, approve
    design-team.md                #     Phase 2 — specialist workers + synthesis
    design-team-context-retrieval.md  # context retrieval for design team
    design-team-lifecycle.md      #     agent teams lifecycle details
    spec-review.md                #     Phase 3 — write and validate design spec
    planning.md                   #     Phase 4 — detailed TDD implementation plan
    plan-format.md                #     plan document template + task structure
    planning-next-steps.md        #     risk signals + second-opinion gate
    execution.md                  #     Phase 5 — task teams + audit loops
    execution-reminders.md        #     mid-execution progress reminders
    audit-loop.md                 #     audit team dispatch + triage
    doc-drift-scan.md             #     documentation drift scan
    post-execution-review.md      #     risk signals + Codex review
    ci-fix-protocol.md            #     CI failure classification + retry protocol
    completion.md                 #     Phase 6 — verify, merge/PR, learning loop
    memory-nudge.md               #     session learning extraction
    reference-files.md            #     index of all reference files
  references/                     #   on-demand reference material
    builder-reference.md          #     builder agent reference
hooks/                            # Claude Code hooks (8 active, deployed to ~/.claude/hooks/)
  builder-self-check.py           #   validates builder agent output quality
  codesight-hooks.py              #   codesight indexing integration
  coding-team-lifecycle.py        #   session lifecycle management (start/end markers)
  git-safety-guard.py             #   prevents force push, main branch commits, etc.
  hook-health-check.py            #   SessionStart — verifies all Python hooks are healthy
  lint-warning-enforcer.py        #   treats lint warnings as errors
  loop-detection.py               #   detects and breaks agent retry loops
  write-guard.py                  #   blocks orchestrator edits to instruction files during Phase 5
  _lib/                           #   shared hook utilities
    __init__.py
    event.py                      #     event parsing
    git.py                        #     git operations
    output.py                     #     output formatting
    state.py                      #     session state management
    suppression.py                #     suppression logic
  tests/                          #   hook test suite (pytest)
scripts/                          # deployment and infrastructure scripts
  deploy.sh                       #   sync hooks, agents, rules, config from repo to ~/.claude/
  statusline-command.sh           #   Claude Code status line formatting
agents/                           # native agent definitions (deployed to ~/.claude/agents/)
  ct-builder.md                   #   builder agent — orchestrates build pipeline
  ct-reviewer.md                  #   code reviewer agent
  ct-qa.md                        #   QA agent — end-to-end quality checks
  ct-plan-reviewer.md             #   plan document reviewer
  ct-prompt-reviewer.md           #   prompt/skill quality reviewer
  ct-harden-reviewer.md           #   security/resilience reviewer
  ct-implementer.md               #   implementer agent template
  ct-spec-reviewer.md             #   spec compliance + TDD verification (read-only)
  ct-simplify-auditor.md          #   simplify auditor — clarity/complexity (read-only)
  ct-harden-auditor.md            #   harden auditor — security/resilience (read-only)
  ct-prompt-craft-auditor.md      #   prompt-craft auditor — CC instruction quality (read-only)
  ct-harness-engineer.md          #   harness engineer — hooks, rules, maturity (read-write)
  ct-spec-doc-reviewer.md         #   design doc reviewer
  ct-plan-doc-reviewer.md         #   plan doc reviewer
  ct-qa-reviewer.md               #   QA reviewer — cross-task quality
  harness-engineer-reference.md   #   on-demand reference for harness engineer
  implementer-reference.md        #   on-demand reference for implementer
config/                           # global instruction files (deployed to ~/.claude/)
  CLAUDE.md                       #   global CLAUDE.md — role, boundaries, workflow prefs
  golden-principles.md            #   16 tiebreaker principles for ambiguous decisions
  code-style.md                   #   language-specific style rules (Python, TS, JS, HTML, SCSS, Rust)
rules/                            # path-specific rules (deployed to ~/.claude/rules/)
  test-files.md                   #   test file rules — real implementations, no mocks
  config-files.md                 #   config file rules — no secrets, validate syntax
  migration-files.md              #   migration rules — never modify deployed, include rollback
  dark-features.md                #   dark feature detection — verify reachability
  precomputation.md               #   pre-computation for orchestrators
  chunk-taxonomy-work.md          #   chunking large analysis tasks
  skill-files.md                  #   skill & CC instruction file rules
  vault-path-resolution.md        #   user-specified paths are authoritative
  hook-bypass.md                  #   hook bypass prevention
  mcp-resilience.md               #   MCP retry limits and graceful degradation
  multi-pass-audit.md             #   multi-pass audit pattern
phases/                           # legacy phase files (mirrors cookbook/phases/)
memory/                           # behavioral feedback (~34 files, persists across sessions)
  MEMORY.md                       #   index — points to consolidated file
  consolidated-feedback.md        #   distilled rules from all feedback (loaded by default)
  active-rules.md                 #   currently active behavioral rules
  feedback-*.md                   #   individual feedback entries (history, not loaded)
  project-*.md                    #   project session notes
  reference-*.md                  #   reference documentation
skills/                           # standalone skills (symlink targets for independent use)
  debug/SKILL.md                  #   /debug — root cause investigation
  verify/SKILL.md                 #   /verify — evidence-before-claims gates
  review-feedback/SKILL.md        #   /review-feedback — handling review feedback
  worktree/SKILL.md               #   /worktree — git worktree setup/cleanup
  parallel-fix/SKILL.md           #   /parallel-fix — parallel agent dispatch
  tdd/SKILL.md                    #   /tdd — test-driven development cycle
  prompt-craft/SKILL.md           #   /prompt-craft — skill & prompt engineering
  harness-engineer/SKILL.md       #   /harness-engineer — harness infrastructure design & audit
  second-opinion/SKILL.md         #   /second-opinion — cross-model second opinion
  scope-lock/SKILL.md             #   /scope-lock — restrict edits to a directory
  scope-unlock/SKILL.md           #   /scope-unlock — remove edit restriction
  release/SKILL.md                #   /release — automated release workflow
  retrospective/SKILL.md          #   /retrospective — engineering retrospective
  doc-sync/SKILL.md               #   /doc-sync — post-ship documentation update
  doc-write/SKILL.md              #   /doc-write — write docs from scratch or improve existing
  dep-audit/SKILL.md              #   /dep-audit — dependency health, license, and upgrade audit
  migration-guide/SKILL.md        #   /migration-guide — breaking change upgrade guides
  onboard/SKILL.md                #   /onboard — guided codebase orientation
  a11y/SKILL.md                   #   accessibility audit — WCAG compliance, keyboard nav, ARIA
  api-qa/SKILL.md                 #   API contract testing — validation, error responses, breaking changes
  incident/SKILL.md               #   incident response — structured production incident coordination
```

## Output files

The skill writes artifacts during execution and at completion:

- `docs/plans/YYYY-MM-DD-<feature>-design.md` — design doc (after Phase 3 approval)
- `docs/plans/YYYY-MM-DD-<feature>.md` — implementation plan (after Phase 4)
- `docs/retros/YYYY-MM-DD-<feature>.md` — retrospective + completion summary (after Phase 6, via `/retrospective`)
- `docs/debug/YYYY-MM-DD-<symptom>.md` — debug reports with architectural notes (via `/debug`)
- `docs/project-evals.md` — accumulated eval criteria fed back to future planning workers (grows over time)

## Troubleshooting: Claude won't use coding-team

If the main agent writes code directly instead of delegating to `/coding-team`, the CLAUDE.md identity framing may have competing signals. The agent's role is 'engineering manager' — any language that implies it should write code conflicts with this identity.

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
| Escape hatch language ("skip", "simple", "trivial") | Agent reclassifies everything as "simple" | Quantify thresholds: "single-file under 20 lines" not "simple" |
| Identity statement not first section | Gets outweighed by surrounding code-writing context | Identity framing must be the first thing the agent reads |

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
