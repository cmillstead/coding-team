# Phase 2: Design Team

Create **one Team Leader task** using `TaskCreate` with: project summary, user's idea, approved approach, and all relevant context from Phase 1.

## Team Leader Responsibilities

1. Decide which specialist workers to spawn, using the sizing heuristics below. Always explain the choice.
2. **Map skills to workers:**
   a. Read `~/.claude/skills/skill-taxonomy.yml`
   b. Identify which categories are relevant to the current task (match task description against category descriptions and skill use-cases)
   c. For each worker, filter to skills whose category lists that worker's role
   d. Build an advisory skill block for each worker's prompt (see format below)
3. Create workers simultaneously via `TaskCreate`. Pass each worker: full context + all sibling task IDs + an explicit **out-of-scope statement** (what this worker should NOT address) + their **skill advisory block**.
4. Wait for all workers (`TaskList`).
5. **Quality check** — before synthesizing, evaluate each worker's output. If a worker's output is off-scope, thin, or clearly low quality: respawn it with a more constrained prompt. Don't patch bad output — scrap and rerun.
6. Cross-review pass (see below).
7. Synthesize into a design doc. Return it.

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

## Cross-Review Pass

**If AGENT_TEAMS_AVAILABLE = true AND team has 4+ workers:**

a. After all workers complete their primary analysis, broadcast a cross-review prompt:
   ```
   SendMessage({
     operation: "broadcast",
     message: "Cross-review phase. Read your siblings' outputs (available in the shared task list). Flag any cross-domain concerns. Message the relevant sibling directly if you need clarification or see a conflict with your own findings. Report cross-domain flags to team-lead when done."
   })
   ```
b. Workers message each other directly to resolve cross-domain questions.
c. Team Leader collects final cross-review flags from each worker's messages.
d. Shutdown workers after collection.

**Otherwise (AGENT_TEAMS_AVAILABLE = false OR team < 4 workers):**

Create follow-up tasks where workers read sibling outputs via `TaskOutput(sibling_id)` and flag cross-domain concerns.

## Team Leader Synthesis

- Resolve conflicts between workers
- Produce design doc covering: architecture, components, data flow, error handling, testing strategy, security considerations
- Flag unresolved trade-offs for user decision

## Skill Taxonomy Maintenance

coding-team reads `~/.claude/skills/skill-taxonomy.yml` to map skills to workers.

- **Installing a skill:** Add it to the appropriate category. If no category fits, create a new one with role mappings.
- **Removing a skill:** Remove its entry from the taxonomy.
- **The taxonomy is advisory** — workers decide which skills to actually invoke based on the task.

## Agent Teams Routing (Design Phase)

| Situation | Agent Teams? | Rationale |
|-----------|-------------|-----------|
| Design workers (primary analysis) | No | Workers analyze independently, report to leader. Subagents are correct. |
| Cross-review pass, 4+ workers | **Yes** | Direct peer messaging for cross-domain flags beats leader-mediated routing. |
| Cross-review pass, <4 workers | No | Small team, leader mediation is fine. |

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
