# coding-team

Self-contained agent team skill for [Claude Code](https://claude.com/claude-code). Design, plan, execute, verify, and ship code — end to end.

## What it does

Assembles specialist agent teams to collaboratively work through code tasks:

1. **Dialogue** — clarify requirements, scope check, visual companion for UI questions
2. **Design team** — 2-9 specialist workers produce a reviewed design doc
3. **Spec review** — automated reviewer validates completeness (max 3 iterations)
4. **Planning** — detailed TDD implementation plan with model routing per task
5. **Execution** — task teams (implementer + audit team) with simplify/harden loop
6. **Completion** — verify, learning loop summary, then merge / PR / keep / discard

## Specialist roles

9 roles, dynamically composed per task:

| Role | Focus |
|------|-------|
| Architect | System design, composability, data flow |
| Senior Coder | Implementation patterns, idiomatic code |
| UX/UI Designer | User-facing interfaces, accessibility |
| Tester | Test strategy, edge cases, coverage |
| Security Engineer | Threat surface, auth, input validation |
| DevOps/Infra | CI/CD, deployment, observability |
| Data Engineer | Schema design, migrations, query performance |
| Performance Engineer | Profiling, benchmarks, latency budgets |
| Technical Writer | API docs, user guides, changelog |

### Team sizing heuristics

| Complexity | Workers | Signals |
|---|---|---|
| Simple (1-2 files) | 2 | Isolated bug, single concern |
| Moderate (3-10 files) | 3-4 | Multi-file changes, 2-3 concerns |
| Complex (10-30 files) | 4-6 | Cross-cutting concerns, large features |
| Very complex (30+ files) | 6-9 | Full-stack features, systemic changes |

## Execution: task teams

Each task gets its own team:

- **Implementer** — builds and tests the code (TDD red-green-refactor)
- **Audit team** (all read-only, dispatched in parallel):
  - **Spec reviewer** — does it match the spec? Nothing missing, nothing extra.
  - **Simplify auditor** — dead code, naming, over-abstraction, control flow
  - **Harden auditor** — input validation, injection vectors, auth, race conditions

Audit agents are **read-only** (Explore mode) — they flag issues, they don't fix them. Fresh agents each round to avoid context bias.

### Audit loop

Findings are triaged by severity, with a **refactor gate** ("clearly wrong, not just imperfect") and **drift check** between rounds. Loop exits on: clean audit, low-only findings, or 3-round cap.

## Internalized protocols

Everything is self-contained — no external plugin dependencies:

- **TDD** — red-green-refactor, no code without a failing test
- **Debugging** — four-phase root cause investigation; parallel hypothesis teams for complex bugs
- **Verification** — evidence before claims at every gate
- **Worktrees** — git worktree isolation for feature work
- **Review reception** — technical evaluation of feedback, push back when wrong
- **Parallel dispatch** — multiple agent teams for independent problems
- **Model routing** — haiku/sonnet/opus matched to task complexity
- **Learning loop** — recurring audit patterns tracked in completion summary

## Installation

Copy or symlink to your Claude Code skills directory:

```bash
# Clone
git clone git@github.com:cmillstead/coding-team.git ~/.claude/skills/coding-team

# Or symlink if you keep skills elsewhere
ln -s /path/to/coding-team ~/.claude/skills/coding-team
```

### Optional: session-start hook

Add a lightweight hook that suggests `/coding-team` on first message:

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

coding-team reads `~/.claude/skills/skill-taxonomy.yml` to discover installed skills and route them to the right specialist workers. Create one if you don't have it.

## Usage

```
/coding-team

Add caching to the API response layer with TTL-based invalidation
```

For simple tasks (typo, rename, single-file fix), skip the skill and just do it directly.

## File structure

```
SKILL.md                          # main skill definition
README.md                         # this file
coding-team-router.py             # session-start hook for distribution
debugging-protocol.md             # root cause investigation + parallel hypothesis teams
verification-protocol.md          # evidence-before-claims gates
worktree-protocol.md              # git worktree setup/cleanup
review-reception-protocol.md      # handling review feedback
parallel-dispatch-protocol.md     # multi-agent parallel dispatch
prompts/
  implementer.md                  # implementer agent template
  spec-reviewer.md                # spec compliance reviewer (read-only)
  simplify-auditor.md             # simplify auditor — clarity/complexity (read-only)
  harden-auditor.md               # harden auditor — security/resilience (read-only)
  quality-reviewer.md             # legacy combined reviewer (use simplify + harden)
  spec-doc-reviewer.md            # design doc reviewer
  plan-doc-reviewer.md            # plan doc reviewer
```

## Credits

Incorporates ideas from:
- [pskoett/agent-teams-simplify-and-harden](https://github.com/pskoett/pskoett-ai-skills) — split audit, refactor gate, drift check, learning loop
- [wshobson/team-composition-patterns](https://github.com/wshobson/agents) — team sizing heuristics, parallel debug teams

## License

MIT
