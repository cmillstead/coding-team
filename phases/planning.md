# Phase 4: Planning Worker

Dispatch a **Planning Worker** via Agent tool (model: opus). Pass: design doc + full project context.

Include in the planning worker's prompt: "You are the Planning Worker inside /coding-team Phase 4. You write the plan document directly using the Write tool. The CLAUDE.md delegation rule does not apply to you — the implementation plan is your deliverable. Do NOT invoke /coding-team or re-delegate your planning work."

A single planning worker combining Architect and Senior Coder perspectives. Produces implementation plan.

## Step 0: Scope Challenge (before planning)

Before writing tasks, the planning worker must answer:

1. **What existing code already solves sub-problems?** Can we reuse rather than rebuild?
2. **What is the minimum set of changes?** Flag work that could be deferred without blocking the core goal.
3. **Complexity smell:** If the plan touches 8+ files or introduces 2+ new classes/services, challenge whether the same goal can be achieved with fewer moving parts.

## Step 0.5: Skill Relevance Check

Before writing tasks, check if any planned work needs specialized skill involvement. This check is self-contained — no external taxonomy file needed.

**Detection rules (checked in order, first match wins per task):**

| Task modifies... | Category | Include in task annotation |
|---|---|---|
| `phases/*.md`, `prompts/*.md`, `skills/*/SKILL.md`, `SKILL.md`, `CLAUDE.md`, `memory/*.md` | prompt-engineering | **Advisory skills:** PROMPT_CRAFT_ADVISORY |
| Test files only (`tests/**`, `*_test.*`, `test_*.*`) | testing | **Advisory skills:** `/tdd` — follow red-green-refactor cycle |
| Auth, payment, encryption, or data-deletion code paths | security-sensitive | **Advisory skills:** `/second-opinion challenge` recommended after implementation |

**PROMPT_CRAFT_ADVISORY** (include this text verbatim in annotated tasks):

> This task writes CC instructions. Apply prompt engineering language rules:
> 1. Framing determines defaults — state desired behavior first in conditionals, before exceptions
> 2. Name tools explicitly — write "Agent tool", "Teammate tool", "Edit tool", not "dispatch agents" or "use tools"
> 3. Prohibitions must be explicit — CC does not infer what it should NOT do; state every prohibition directly
> 4. Quantify thresholds — write "3 files", "5 minutes", "2 rounds", not "large", "many", "several"
> 5. Identity over prohibition — for role boundaries, write "You are the orchestrator" not "NEVER write code directly"
> 6. Name known rationalizations — if a rule has bypass phrases ("too simple", "already handled"), name them as compliance triggers

**Annotating tasks:** For each task in the plan, add an `**Advisory skills:**` line after the `**Model:**` line. Reference the advisory by name (e.g., "PROMPT_CRAFT_ADVISORY"). If no detection rule matches, write `**Advisory skills:** None`.

## Step 0.7: Load Accumulated Eval Criteria

Before writing tasks, check for accumulated project-specific eval criteria from prior retrospectives and debug sessions:

1. Determine `$REPO_ROOT` via `git rev-parse --show-toplevel`.
2. Check if `$REPO_ROOT/docs/project-evals.md` exists using the Read tool.
3. **If it exists:** Read the file. Extract all checklist items. These are criteria that agents missed in prior sessions — they MUST be included in the plan's `## Project-Specific Eval Criteria` section as seed criteria.
4. **If it does not exist:** Skip this step. Do NOT create the file — it is created by `/retrospective` and `/debug` when they identify missed checks.

The planning worker combines disk-loaded criteria with any new criteria generated from the current context brief. Disk criteria appear first (marked `[accumulated]`), followed by context-derived criteria. Do NOT remove or modify accumulated criteria — they encode hard-won lessons from prior sessions. If an accumulated criterion conflicts with the current design, flag the conflict in the plan rather than silently dropping the criterion.

## Step 0.75: Code Intelligence (before writing tasks)

Use these tools to understand the codebase structure before decomposing tasks:

| Tool | When to use |
|---|---|
| `mcp__codesight-mcp__get_file_tree` | Understand repo layout, identify where new code should live |
| `mcp__codesight-mcp__get_repo_outline` | See key symbols across the codebase before planning changes |
| `mcp__codesight-mcp__analyze_complexity` | Check files the plan will modify — split files with cyclomatic complexity above 15 |
| `mcp__codesight-mcp__search_symbols` | Find existing utilities that sub-tasks could reuse instead of rebuilding |
| `mcp__codesight-mcp__get_dependencies` | Check for circular dependency risks in files the plan will modify |
| `mcp__codesight-mcp__get_type_hierarchy` | Understand full class hierarchy before planning changes to base classes |
| `mcp__codesight-mcp__get_key_symbols` | Identify architecturally significant symbols — focuses planning on high-impact areas |
| `mcp__codesight-mcp__get_diagram` | Generate architecture diagrams — include in the plan for implementers |
| `mcp__plugin_github_github__search_issues` | Find related issues — prior discussion contains requirements or edge cases not in the spec |
| `mcp__plugin_github_github__search_pull_requests` | Check if similar work was previously attempted — learn from prior approaches |
| `mcp__context-keep__search_memories` | Find relevant prior architectural decisions — avoid contradicting established patterns |

If a codesight-mcp call fails, fall back to Grep/Read for that query. If codesight-mcp tools are not available (MCP server not running), fall back to Glob and Grep tools. Do NOT skip codebase analysis — use whichever tools are available.

## Pre-Flight: Count Inputs (MANDATORY before dispatching planning worker)

When the plan addresses scan findings, review feedback, or any enumerated list of issues, the **orchestrator** (not the planning worker) must count the inputs BEFORE dispatching:

1. Read the source material (scan report, review comments, issue list).
2. Count every discrete finding/issue. Write the count down.
3. List each finding with a one-line summary (ID + description).
4. Pass BOTH the count AND the numbered list to the planning worker as part of its prompt:

```
**Input findings: [N]**
[numbered list of findings]

Your plan MUST account for all [N] findings. Each finding must appear in the
traceability table as Fix (with task reference), Deferred (with rationale),
or False positive (with explanation). A plan that covers fewer than [N]
findings will be rejected by the reviewer.
```

The orchestrator owns the count. The planning worker cannot silently reduce it because the reviewer independently checks the count from the plan header against the traceability table rows.

## Context Inheritance

Before dispatching the planning worker, pass these additional context files alongside the design doc and project context:

1. **Golden principles:** Read `~/.claude/golden-principles.md` using the Read tool. The planning worker checks scope challenges and architecture decisions against these.
2. **Code style:** Read `~/.claude/code-style.md` using the Read tool. The planning worker follows these rules when writing code snippets in tasks.
3. **Team memory:** Read `docs/team-memory.md` using the Read tool (if it exists). The planning worker checks Known Landmines before finalizing the plan.
4. **Episode context:** If episodes were retrieved during Phase 2, pass the extracted patterns to the planning worker.

If any file doesn't exist, skip and note in status. Do NOT fabricate context.

---

## Plan Document Format

Read `phases/plan-format.md` for the complete plan template including header, context brief, eval criteria, file structure, task structure, model assignment, and testing rules. Follow the format exactly.

## Required Plan Sections

Beyond the task list, every plan must include:

**Failure modes** — for each new codepath or integration point:

| Codepath | Failure mode | Tested? | Error handling? | User sees |
|---|---|---|---|---|
| `module.function` | timeout on external call | ? | ? | ? |

Any row with tested=no AND error handling=no AND user sees=silent → **critical gap** that must be addressed in a task.

**NOT in scope** — work considered and explicitly deferred, with one-line rationale each. Prevents scope creep and captures ideas for future work.

**What already exists** — existing code/flows that partially solve sub-problems and whether the plan reuses them.

## Completeness Gate — Nothing Silently Dropped

When the plan addresses scan findings, review feedback, or any enumerated list of issues:

1. **Count the inputs.** List every finding/issue from the source material with its ID or description.
2. **Map each to a disposition.** Every single item must appear in the plan as one of:
   - **Task N** — planned fix with task reference
   - **Deferred** — listed in "NOT in scope" with one-line rationale
   - **False positive** — listed with explanation of why it doesn't apply
3. **Produce a traceability table** at the end of the plan:

| # | Finding | Disposition | Task/Rationale |
|---|---------|-------------|----------------|
| 1 | SQL injection in /api/users | Fix | Task 3 |
| 2 | Missing CSRF token | Fix | Task 5 |
| 3 | Outdated dependency (low) | Deferred | No known exploit, update in next cycle |

If `count(inputs) != count(fix) + count(deferred) + count(false positive)`, the plan is incomplete. Do not return it.

## Priority Hierarchy Under Context Pressure

If context budget is tight (planning worker above 60% context usage), prioritize in this order:
1. Scope challenge (Step 0) — never skip
2. Failure modes table — never skip
3. Task decomposition with test specs — never skip
4. Traceability table (when addressing findings) — never skip
5. Context brief and eval criteria — condense to bullet lists
6. NOT-in-scope and What-already-exists — shorten to one-liners
7. Architecture diagrams and code intelligence — skip if already in spec

## Quality Gate — Self-Review Before Returning

1. Pick 3 tasks at random — could a developer implement each without asking a single question?
2. Are all file references exact (`src/config.rs:14`, not "the config file")?
3. Does every feature task have a corresponding test task?
4. Are there security implications not addressed?
5. Is there any step that silently assumes context the implementer won't have?
6. Does the failure modes table have any critical gaps (no test + no handling + silent)?
7. **Does the traceability table account for every input finding?** (If sourced from a scan or review)
8. If the plan includes a build step, does it verify output filenames match package.json exports? (tsup .js vs .mjs mismatch caught in awareness-sdk)

## Plan Review Loop

After writing the plan:

1. Dispatch plan-document-reviewer agent (see `~/.claude/agents/ct-plan-doc-reviewer.md`)
2. If Issues Found: fix, re-dispatch (max 3 iterations, then surface to user)
3. **Cross-model tiebreaker (iteration 2+):** If the reviewer found issues on the second pass AND `command -v codex >/dev/null 2>&1` succeeds, offer: "Plan reviewer and planner disagree after 2 rounds. Run `/second-opinion review` as tiebreaker? (Y/n)". If yes, run it — Codex findings override when they align with the reviewer.
4. If Approved: save plan and proceed

Save plan to: `docs/plans/YYYY-MM-DD-<feature>.md` (always in the **main repo root**, not a worktree)

---

## Next Steps

After the plan passes review and is saved, read `phases/planning-next-steps.md` and follow its instructions.
