# coding-team

Self-contained agent team skill for [Claude Code](https://claude.com/claude-code). Design, plan, execute, verify, and ship code — end to end.

## What it does

Assembles specialist agent teams to collaboratively work through code tasks:

1. **Dialogue** — clarify requirements interactively
2. **Design team** — 2-9 specialist workers produce a reviewed design doc
3. **Spec review** — automated reviewer validates completeness
4. **Planning** — detailed TDD implementation plan with model routing
5. **Execution** — task teams (implementer + spec reviewer + quality reviewer) per step
6. **Completion** — verify, then merge / PR / keep / discard

## Specialist roles

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

The team leader picks only the roles the task needs.

## Internalized protocols

Everything is self-contained — no external plugin dependencies:

- **TDD** — red-green-refactor, no code without a failing test
- **Debugging** — four-phase root cause investigation
- **Verification** — evidence before claims at every gate
- **Worktrees** — git worktree isolation for feature work
- **Review reception** — technical evaluation of feedback
- **Parallel dispatch** — multiple agent teams for independent problems
- **Model routing** — haiku/sonnet/opus matched to task complexity

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
debugging-protocol.md             # root cause investigation protocol
verification-protocol.md          # evidence-before-claims gates
worktree-protocol.md              # git worktree setup/cleanup
review-reception-protocol.md      # handling review feedback
parallel-dispatch-protocol.md     # multi-agent parallel dispatch
prompts/
  implementer.md                  # implementer agent template
  spec-reviewer.md                # spec compliance reviewer
  quality-reviewer.md             # code quality reviewer
  spec-doc-reviewer.md            # design doc reviewer
  plan-doc-reviewer.md            # plan doc reviewer
```

## License

MIT
