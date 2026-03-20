# coding-team

Self-contained agent team skill for [Claude Code](https://claude.com/claude-code). Design, plan, execute, verify, and ship code — end to end.

## What it does

Assembles specialist agent teams to collaboratively work through code tasks. The skill routes your request to the right phase, assembles the right team, and manages the full lifecycle:

1. **Dialogue** — clarify requirements, explore approaches, get alignment
2. **Design team** — specialist workers analyze the problem from multiple angles
3. **Spec review** — automated reviewer validates the design doc
4. **Planning** — detailed TDD implementation plan with model routing per task
5. **Execution** — task teams (implementer + audit team) build and verify
6. **Completion** — full verification, learning loop, then merge / PR / keep / discard

## How it works

### Session routing

When invoked, the skill determines where to start based on what you bring:

| You have... | Entry point |
|---|---|
| A vague idea or new feature request | Phase 1 — dialogue to clarify |
| A design or spec, needs a plan | Phase 4 — planning worker |
| A plan file, ready to build | Phase 5 — execution |
| A bug report or test failure | Debugging protocol |
| A PR with review feedback | Review reception protocol |
| Multiple independent failures | Parallel dispatch protocol |
| A trivial task (rename, typo, single-file fix) | Skip the skill — just do it directly |

The skill matches process weight to task weight. A typo fix doesn't need 5 specialist workers.

### Phase 1: Dialogue

The skill reads project context (files, docs, recent commits, CLAUDE.md), then asks clarifying questions one at a time — multiple choice preferred, open-ended when needed. For UI-related work, a visual companion is offered before continuing.

Once requirements are clear, 2-3 approaches are proposed with trade-offs:
- At least one **minimal viable** approach (smallest diff)
- At least one **ideal architecture** approach (best long-term trajectory)
- For complex features, a **dream state** sketch: current state -> this plan -> 12-month ideal

No work begins until you approve an approach.

### Phase 2: Design team

A Team Leader spawns specialist workers to analyze the problem from different angles. Workers run in parallel and are composed dynamically based on what the task needs.

**Specialist roles:**

| Role | Focus | Skip when |
|------|-------|-----------|
| Architect | System design, composability, data flow | Trivial bug fixes |
| Senior Coder | Implementation approach, patterns, idiomatic code | Never |
| UX/UI Designer | First-run UX, error messages, discoverability | Pure backend / no user-facing surface |
| Tester | Test strategy, edge cases, coverage | Never |
| Security Engineer | Trust boundaries, input validation, threat model | Pure refactors with no new surface area |
| DevOps/Infra | CI/CD, deployment, observability | No deployment or infra changes |
| Data Engineer | Schema design, migrations, query performance | No data layer changes |
| Performance Engineer | Profiling, benchmarks, latency budgets | No performance-sensitive paths |
| Technical Writer | API docs, user guides, changelog | No public-facing or doc surface |

**Team sizing:**

| Complexity | Workers | Signals |
|---|---|---|
| Simple (1-2 files) | 2 | Isolated bug, single concern |
| Moderate (3-10 files) | 3-4 | Multi-file changes, 2-3 concerns |
| Complex (10-30 files) | 4-6 | Cross-cutting concerns, large features |
| Very complex (30+ files) | 6-9 | Full-stack features, systemic changes |

Workers produce findings, concerns, and recommendations from their specialist lens. A cross-review pass lets workers read sibling outputs and flag cross-domain issues. The Team Leader synthesizes everything into a design doc, resolving conflicts and flagging unresolved trade-offs for your decision.

**Quality check:** If a worker's output is thin, off-scope, or low quality, the Team Leader respawns it with a tighter prompt rather than patching around bad output.

### Phase 3: Spec review

After you approve the design, it's written to `docs/plans/YYYY-MM-DD-<feature>-design.md` and passed through an automated spec document reviewer that checks for completeness, consistency, clarity, scope, and YAGNI violations. Up to 3 review iterations before surfacing issues to you. You get a final review before proceeding.

### Phase 4: Planning

A Planning Worker (Architect + Senior Coder) produces a detailed implementation plan. Before writing tasks, it challenges scope:
- What existing code already solves sub-problems?
- What is the minimum set of changes?
- If 8+ files or 2+ new classes — can it be simpler?

**Plan structure:**
- Header with goal, architecture, tech stack
- File structure mapping (which files created/modified and why)
- Tasks with exact file paths, line ranges, complete code, exact commands with expected output
- Each step is one action (2-5 minutes) — no ambiguity
- Failure modes table identifying untested/unhandled error paths
- NOT in scope section preventing scope creep
- What already exists section for reuse

**Model assignment per task:**
- **haiku** — 1-2 files with complete spec, mechanical changes
- **sonnet** — multiple files, needs judgment, integration work
- **opus** — design decisions, broad codebase understanding

The plan goes through an automated plan document reviewer (up to 3 iterations) before being saved to `docs/plans/YYYY-MM-DD-<feature>.md`.

### Phase 5: Execution

Before the first task, the full test suite runs to establish a **baseline**. If any tests are already failing, the first implementer fixes them before starting task work — no pre-existing failure is dismissed as "not our problem."

Each task gets its own **task team**:

**Implementer** builds using TDD (red-green-refactor), then reports one of four statuses:
- **DONE** — proceed to audit
- **DONE_WITH_CONCERNS** — concerns assessed before audit
- **NEEDS_CONTEXT** — missing info provided, re-dispatched
- **BLOCKED** — assessed and escalated (more context, stronger model, smaller tasks, or user escalation)

**Audit team** (all read-only, dispatched in parallel after implementer reports DONE):
- **Spec reviewer** — does the code match the spec? Was TDD actually followed? Independently verifies by reading code, not trusting the implementer's report.
- **Simplify auditor** — dead code, naming, over-abstraction, control flow. Only flags things that are "clearly wrong, not just imperfect."
- **Harden auditor** — input validation, injection vectors, auth, race conditions, secrets, resource exhaustion. Focuses on exploitable issues, not theoretical risks.

Audit agents are read-only (Explore mode) — they flag issues, they don't fix them. Fresh agents each round to avoid context bias.

**Audit triage:**
- **Refactor gate** — "Would a senior engineer say this is clearly wrong, not just imperfect?" Rejects style preferences and marginal improvements.
- **Severity routing** — critical/high fixed immediately, medium in next round, low/cosmetic fixed inline if trivial or noted and skipped.
- **Budget check** — if fix rounds add 30%+ to the original diff, tighten scope.
- **Drift check** — re-read original task description between rounds to prevent scope creep.

The audit loop exits on: clean audit, low-only findings, or 3-round cap.

### Phase 6: Completion

After all tasks pass verification (fresh test output required), four options are presented:

1. **Merge locally** — checkout base, pull, merge, verify tests on merged result, delete feature branch, cleanup worktree
2. **Push and create PR** — push, create PR with summary and test plan
3. **Keep as-is** — report branch name and worktree path
4. **Discard** — requires typing "discard" to confirm

A **learning loop summary** captures recurring audit patterns across all rounds, unresolved low-severity findings, and out-of-scope observations.

## Internalized protocols

Everything is self-contained — no external plugin dependencies.

### TDD

All implementation follows test-driven development:

1. **RED** — write one failing test showing desired behavior
2. **Verify RED** — run test, confirm it fails for the right reason (feature missing, not typo)
3. **GREEN** — write minimal code to pass the test
4. **Verify GREEN** — run test, confirm it passes, no other tests broken
5. **REFACTOR** — clean up, keep tests green
6. **Repeat**

If code is written before a test: delete it, start over with the test.

### Debugging

Four-phase root cause investigation (`debugging-protocol.md`):

1. **Investigate** — read errors completely, reproduce, check recent changes, trace data flow
2. **Analyze** — match against known patterns (race conditions, nil propagation, state corruption, integration failures, config drift, stale cache), check git log for prior fixes in same area
3. **Hypothesize** — simple bugs: sequential single hypothesis. Complex bugs with multiple plausible causes: dispatch parallel debug team (one read-only Explore agent per hypothesis, investigating concurrently)
4. **Implement** — create failing test, fix root cause, verify

**Iron law:** no fixes without root cause investigation. If 3+ fix attempts fail, question the architecture and escalate to user.

### Verification

Evidence-before-claims gates (`verification-protocol.md`):

1. **IDENTIFY** — what command proves the claim?
2. **RUN** — execute the full command (fresh, in this message)
3. **READ** — full output, check exit code
4. **VERIFY** — does output confirm the claim?
5. **ONLY THEN** — make the claim

No "should pass," no "looks correct," no trusting agent reports without independent verification. Applied at every phase transition and before any completion claim.

### Worktrees

Git worktree isolation for feature work (`worktree-protocol.md`). Creates an isolated copy of the repo with a feature branch, runs project setup, verifies a clean baseline. Offered for non-trivial tasks. Cleanup depends on completion choice — merged/discarded worktrees are removed, kept/pushed worktrees stay.

### Review reception

Technical evaluation of feedback (`review-reception-protocol.md`). Read, understand, verify against codebase reality, evaluate technically, then respond or push back with reasoning. No performative agreement ("Great point!") — just fix it or discuss technically. Push back when feedback breaks existing functionality, lacks context, violates YAGNI, or is technically incorrect.

### Parallel dispatch

Multiple agent teams for independent problems (`parallel-dispatch-protocol.md`). When 3+ failures have different root causes in independent subsystems, dispatch one team per domain in parallel. Each team gets focused scope, clear context, constraints, and expected output format. Results are reviewed for conflicts and verified with a full test suite run.

### Model routing

Uses the cheapest model that can handle each task:

| Task type | Model | Examples |
|-----------|-------|---------|
| Mechanical | haiku | Single file edits, formatting, simple rewrites |
| Implementation | sonnet | Feature implementation, test writing, multi-file refactoring |
| Architecture/review | opus | Planning, design, spec review, complex debugging |

If a cheaper model fails or returns low-quality results, the task is re-dispatched with the next tier up.

## Installation

Clone to your skills directory:

```bash
git clone git@github.com:cmillstead/coding-team.git ~/.claude/skills/coding-team
```

Or symlink if you keep skills elsewhere:

```bash
ln -s /path/to/coding-team ~/.claude/skills/coding-team
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

For simple tasks (typo, rename, single-file fix), skip the skill and just do it directly.

## Guiding principles

- **Scrap, don't fix** — if a worker's output is thin or off-scope, respawn it rather than patching around it
- **Never mock what you can use for real** — only mock external systems genuinely unavailable in the test environment
- **Quality gates before handoff** — no agent passes work until tests pass and linting is clean
- **Focused agents produce correct agents** — one worker, one lens, one scope
- **No ambiguity in specs** — exact file paths, exact line ranges, complete code, exact commands
- **Evidence before claims** — no completion claims without fresh verification output
- **Right-size the model** — use the cheapest model that can handle the task

## File structure

```
SKILL.md                          # full skill definition (implementation spec)
README.md                         # this file (user guide)
coding-team-router.py             # session-start hook
debugging-protocol.md             # root cause investigation + parallel hypothesis teams
verification-protocol.md          # evidence-before-claims gates
worktree-protocol.md              # git worktree setup/cleanup
review-reception-protocol.md      # handling review feedback
parallel-dispatch-protocol.md     # multi-agent parallel dispatch
prompts/
  implementer.md                  # implementer agent template
  spec-reviewer.md                # spec compliance + TDD verification (read-only)
  simplify-auditor.md             # simplify auditor — clarity/complexity (read-only)
  harden-auditor.md               # harden auditor — security/resilience (read-only)
  quality-reviewer.md             # legacy combined reviewer (use simplify + harden)
  spec-doc-reviewer.md            # design doc reviewer
  plan-doc-reviewer.md            # plan doc reviewer
```

## Output files

The skill writes two artifacts during execution:

- `docs/plans/YYYY-MM-DD-<feature>-design.md` — design doc (after Phase 3 approval)
- `docs/plans/YYYY-MM-DD-<feature>.md` — implementation plan (after Phase 4)

## Credits

Incorporates ideas from:
- [superpowers](https://github.com/anthropics/claude-plugins-official) — TDD, verification gates, systematic debugging, worktrees, code review, plan execution
- [gstack](https://github.com/garrytan/gstack) — investigate, review, ship, and design review workflows
- [pskoett/agent-teams-simplify-and-harden](https://github.com/pskoett/pskoett-ai-skills) — split audit, refactor gate, drift check, learning loop
- [wshobson/team-composition-patterns](https://github.com/wshobson/agents) — team sizing heuristics, parallel debug teams
- [alinaqi/claude-bootstrap](https://github.com/alinaqi/claude-bootstrap) — independent TDD verification

## License

MIT
