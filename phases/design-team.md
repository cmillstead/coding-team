# Phase 2: Design Team

**If AGENT_TEAMS_AVAILABLE = true:**

1. Create team:
   `Teammate({ operation: "spawnTeam", team_name: "design-<feature>" })`

2. Spawn a Team Leader teammate with: project summary, user's idea, approved approach, and all relevant context from Phase 1.

The Team Leader then:
1. Decides which specialist workers to spawn (see sizing heuristics below). Always explains the choice.
2. Maps skills to workers (see skill advisory block format below).
3. Creates tasks for each specialist via `TaskCreate` on the shared task list.
   - Each teammate gets: full context, sibling task IDs, explicit out-of-scope statement, skill advisory block.
4. Spawns each specialist as a teammate via the Task tool with `team_name`.
5. Monitors `TaskList` for completion. Checks inbox for messages.
6. Quality check — if a worker's output is off-scope, thin, or low quality: respawn with a tighter prompt. Don't patch bad output — scrap and rerun.
7. Cross-review pass — broadcasts to all teammates to read sibling outputs and flag cross-domain concerns. Workers message each other directly.
8. Synthesizes findings into a design doc.
9. Shuts down all teammates, runs cleanup, returns design doc.

**If AGENT_TEAMS_AVAILABLE = false:**

Create **one Team Leader task** using the Agent tool with: project summary, user's idea, approved approach, and all relevant context from Phase 1.

The Team Leader then:
1. Decides which specialist workers to spawn.
2. Maps skills to workers.
3. Creates workers simultaneously via the Agent tool.
4. Waits for all workers.
5. Quality check — respawn bad output.
6. Cross-review pass — creates follow-up tasks where workers read sibling outputs via `TaskOutput(sibling_id)`.
7. Synthesizes into a design doc. Returns it.

---

## Skill Advisory Block Format

Included in each worker's prompt:

> ## Available Skills
>
> The following skills are installed and relevant to this task.
> Invoke any that would strengthen your analysis using the Skill tool.
>
> - `skill-name` — one-line description of when to use it

If no skills match a worker's role + the task's categories, omit the block for that worker.

## Specialist Roles

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
| Prompt/Skill Specialist | Prompt quality, skill coverage, agent coordination patterns, instruction clarity | No prompt/skill changes in scope |

## Team Sizing Heuristics

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

## Worker Output Format

- Findings from their specialist lens
- Concerns or risks with the proposed approach
- Recommendations and alternatives
- Cross-domain flags after reading sibling outputs

## Team Leader Synthesis

- Resolve conflicts between workers
- Produce design doc covering: architecture, components, data flow, error handling, testing strategy, security considerations
- Flag unresolved trade-offs for user decision

## Skill Taxonomy Maintenance

coding-team reads `~/.claude/skills/skill-taxonomy.yml` to map skills to workers.

- **Installing a skill:** Add it to the appropriate category. If no category fits, create a new one with role mappings.
- **Removing a skill:** Remove its entry from the taxonomy.
- **The taxonomy is advisory** — workers decide which skills to actually invoke based on the task.

## Coordination Mode

**Evaluate the three signals** (see SKILL.md Step 0):
- COORDINATION: **Yes** — specialists analyze cross-domain concerns, one worker's findings affect another's approach
- DISCOVERY: **Yes** — analyzing unknown codebase, scope of findings unknown upfront
- COMPLEXITY: **Yes** — design decisions, architectural trade-offs

Design work almost always routes to agent teams when available. The Team Leader is a teammate, specialists are teammates, cross-review uses direct messaging.

When AGENT_TEAMS_AVAILABLE = false: all design work uses subagents via the Agent tool.

## Agent Teams Lifecycle

All agent team usage follows this lifecycle:

```
1. CREATE TEAM
   Teammate({ operation: "spawnTeam", team_name: "<descriptive-name>" })

2. CREATE TASKS
   TaskCreate({ subject, description, activeForm })
   - Set dependencies with blocked_by if tasks have ordering requirements

3. SPAWN TEAMMATES
   Use Task tool with team_name parameter to spawn into the team
   - Each teammate gets: full context, clear scope, constraints, output format
   - Teammates auto-load CLAUDE.md, MCP servers, and skills
   - Teammates do NOT inherit lead's conversation history — include everything they need in the spawn prompt

4. COORDINATE
   - Monitor via TaskList for task status
   - Check inbox for messages from teammates
   - Broadcast when all teammates need the same information
   - Direct message for targeted coordination

5. SHUTDOWN
   For each teammate:
     Teammate({ operation: "requestShutdown", target_agent_id: "<id>" })
   Wait for each to approve (they finish current work first)

6. CLEANUP
   Teammate({ operation: "cleanup" })
   - Only the lead runs cleanup
   - Verify all teammates are shut down before cleanup
   - Cleanup removes shared team resources (inbox, config, task files)
```

**Never:**
- Let teammates run cleanup (their team context may not resolve correctly)
- Skip shutdown and go straight to cleanup (check for active teammates first)
- Spawn teammates without the team existing (spawnTeam first)
- Forget to include task-specific context in spawn prompts (teammates have no conversation history)

---

## Next Steps

After the user approves the design doc, print this block VERBATIM (do not paraphrase, reorder, or omit lines):

> ---
>
> **Design doc approved.**
>
> **Next:** Phase 3 will write the spec and run automated review. "Proceed to Phase 3"
>
> **After Phase 3:** The spec gets written to `docs/plans/`. Then Phase 4 produces the implementation plan.
>
> **Context check:** If the design discussion was extensive, this is a viable clear point.
>
> **Optional before proceeding:**
> - `/codex consult "Is this architecture sound?"` — independent perspective from a different model
> - `/prompt-craft audit` — if the design involves new agent prompts or skills, audit them now before they're baked into the plan
>
> ---
