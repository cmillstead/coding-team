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

**Annotating tasks:** For each task in the plan, add an `**Advisory skills:**` line after the `**Model:**` line. Reference the advisory by name (e.g., "PROMPT_CRAFT_ADVISORY"). If no detection rule matches, write `**Advisory skills:** None`.

## Step 0.7: Load Accumulated Eval Criteria

Before writing tasks, check for accumulated project-specific eval criteria from prior retrospectives and debug sessions:

1. Determine `$REPO_ROOT` via `git rev-parse --show-toplevel`.
2. Check if `$REPO_ROOT/docs/project-evals.md` exists using the Read tool.
3. **If it exists:** Read the file. Extract all checklist items. These are criteria that agents missed in prior sessions — they MUST be included in the plan's `## Project-Specific Eval Criteria` section as seed criteria.
4. **If it does not exist:** Skip this step. Do NOT create the file — it is created by `/retrospective` and `/debug` when they identify missed checks.

The planning worker combines disk-loaded criteria with any new criteria generated from the current context brief. Disk criteria appear first (marked `[accumulated]`), followed by context-derived criteria. Do NOT remove or modify accumulated criteria — they encode hard-won lessons from prior sessions. If an accumulated criterion conflicts with the current design, flag the conflict in the plan rather than silently dropping the criterion.

## Step 0.75: Code Intelligence (before writing tasks)

Use codesight-mcp tools to understand the codebase structure before decomposing tasks:

- Use `mcp__codesight-mcp__get_file_tree` to understand the repository layout and identify where new code should live.
- Use `mcp__codesight-mcp__get_repo_outline` to see key symbols across the codebase — understand the architecture before planning changes.
- Use `mcp__codesight-mcp__analyze_complexity` on files the plan will modify — high-complexity files (cyclomatic complexity above 15) may need to be split or refactored as part of the task.
- Use `mcp__codesight-mcp__search_symbols` to find existing utilities that sub-tasks could reuse instead of rebuilding.
- Use `mcp__codesight-mcp__get_dependencies` to check for circular dependency risks in files the plan will modify — circular imports block clean task decomposition.
- Use `mcp__codesight-mcp__get_type_hierarchy` when the plan involves class hierarchies or inheritance — understand the full tree before planning changes to base classes.
- Use `mcp__plugin_github_github__search_issues` to find related issues in the repository — prior discussion often contains requirements or edge cases not in the spec.
- Use `mcp__plugin_github_github__search_pull_requests` to check if similar work was previously attempted — learn from prior approaches and their outcomes.
- Use `mcp__context-keep__search_memories` to find relevant prior architectural decisions — avoid contradicting established patterns without explicit rationale.
- Use `mcp__codesight-mcp__get_key_symbols` to identify the most architecturally significant symbols — focuses planning on high-impact areas and key entry points.
- Use `mcp__codesight-mcp__get_diagram` to generate architecture diagrams — include in the plan document to help implementers understand the system structure.

If codesight-mcp tools are not available (MCP server not running), fall back to Glob and Grep tools. Do NOT skip codebase analysis — use whichever tools are available.

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

If any file doesn't exist, skip it. Do NOT fabricate context.

---

## Plan Document Format

Every plan starts with this header:

```markdown
# [Feature Name] Implementation Plan

**Input findings: [N]** ← include ONLY when addressing scan/review findings; omit for feature work

**Goal:** [One sentence describing what this builds]

**Architecture:** [2-3 sentences about approach]

**Tech Stack:** [Key technologies/libraries]

---
```

## Context Brief

After the header, every plan includes a context brief. The planning worker fills this from the design doc, project knowledge, and CLAUDE.md.

```markdown
## Context Brief

> Non-obvious project context that implementers need. Skip any field that doesn't apply.

- **Environment:** [production/staging/greenfield — what data or users are at risk]
- **Sacred paths:** [files, databases, or infrastructure that must not be modified without explicit confirmation]
- **Decision history:** [key architectural decisions relevant to this work and why they were made]
- **External dependencies:** [APIs, services, vendor relationships that constrain this work]
- **Known landmines:** [areas where technically correct changes have caused problems before]
```

The planning worker MUST fill this section. If no organizational context is known, write: "No non-obvious context identified. Standard development environment."
Do NOT invent context you do not have evidence for. If a field's answer is unknown, omit the field entirely. Fabricated context is worse than no context — it causes implementers to work around constraints that don't exist.

## Project-Specific Eval Criteria (optional)

The planning worker produces eval criteria from two sources: (1) accumulated criteria loaded from `$REPO_ROOT/docs/project-evals.md` in Step 0.7, and (2) new criteria generated from the current context brief. Auditors MUST check all listed criteria beyond their standard lens.

```markdown
## Project-Specific Eval Criteria

> Domain-specific checks that auditors MUST verify beyond their standard lens. These encode project context that generic audits miss.

### Accumulated (from prior sessions)
- [ ] [accumulated criterion from docs/project-evals.md]

### Context-derived (this session)
- [ ] [Criterion — e.g., "No destructive database operations without rollback mechanism"]
- [ ] [Criterion — e.g., "MCP message handling changes must preserve backward compatibility"]
```

If the context brief has no domain-specific constraints, omit this section entirely. Do NOT generate generic criteria — they must encode actual project context. Generic criteria like "code should be well-tested" add noise, not signal.

## File Structure

Before defining tasks, map out which files will be created or modified and what each one is responsible for. Design units with clear boundaries and well-defined interfaces. Prefer smaller, focused files.

## Task Structure

````markdown
### Task N: [Component Name]

**Files:**
- Create: `exact/path/to/file.py`
- Modify: `exact/path/to/existing.py:123-145`
- Test: `tests/exact/path/to/test.py`

**Model:** haiku | sonnet | opus

- [ ] **Step 1: Write the failing test**

```python
def test_specific_behavior():
    result = function(input)
    assert result == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/path/test.py::test_name -v`
Expected: FAIL with "function not defined"

- [ ] **Step 3: Write minimal implementation**

```python
def function(input):
    return expected
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/path/test.py::test_name -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/path/test.py src/path/file.py
git commit -m "feat: add specific feature"
```
````

**Each step is one action (2-5 minutes).** Complete code in plan — not "add validation here." Exact commands with expected output.

**Model assignment per task:** The planning worker assigns a model tier to each task:
- **haiku** — touches 1-2 files with complete spec, mechanical changes
- **sonnet** — touches multiple files, needs judgment, integration work
- **opus** — requires design decisions, broad codebase understanding

**Testing rules baked into every plan:**
- Never mock what you can use for real
- Only mock external systems genuinely unavailable in test environment
- Never mock the thing being tested
- Every task batch ends with: run tests -> run linter -> confirm both pass -> commit
- Every status/error mapping table must include a catch-all row ("all other cases → ..."). Design specs that leave the "else" path undefined cause health() / observe() style bugs where unexpected inputs fall through to success paths.

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

1. Dispatch plan-document-reviewer agent (see `prompts/plan-doc-reviewer.md`)
2. If Issues Found: fix, re-dispatch (max 3 iterations, then surface to user)
3. If Approved: save plan and proceed

Save plan to: `docs/plans/YYYY-MM-DD-<feature>.md` (always in the **main repo root**, not a worktree)

---

## Next Steps

After the plan passes review and is saved:

1. Evaluate risk signals against the plan:

| Signal | Detection |
|---|---|
| Plan touches 5+ files | Count files in task list `**Files:**` sections |
| Plan has opus-tier tasks | Any task with `**Model:** opus` |
| Plan introduces new security surface | Tasks touch auth, payment, encryption, session, token, CORS, or CSP files |
| Plan modifies CC instruction files | Tasks touch `phases/*.md`, `skills/*/SKILL.md`, `prompts/*.md`, `CLAUDE.md`, `SKILL.md` |
| Plan includes database migrations | Tasks create or alter schema, migrations, or indexes |
| User previously requested Codex review | User said "codex", "second opinion", or "cross-model" in this session |

2. Run: `command -v codex >/dev/null 2>&1` to check if Codex CLI is available.

3. **If ANY risk signal is true AND Codex is available**, print this VERBATIM (substitute actual values), then STOP — do not print anything after this block. Your next message depends on the user's answer:

> ---
>
> **Plan saved to `docs/plans/<actual-path>`.**
>
> This plan [touches N files / modifies security surface / has opus-tier tasks / etc.].
>
> Run `/second-opinion review` for an independent second opinion on the plan? (Y/n)
>
> ---

   - User says yes: run `/second-opinion review` against the plan file. After Codex review completes, continue with step 4.
   - User says no or sends a different message: continue with step 4.

4. **If no risk signals fire OR Codex is not available OR Codex review is done**, print this VERBATIM (substitute actual values):

> ---
>
> **Plan saved to `docs/plans/<actual-path>`.**
>
> **Next:** Phase 5 execution. "Proceed to Phase 5"
>
> **Recommended before execution:**
> - `/worktree` — set up an isolated workspace (offered automatically)
>
> **Context check:** Check `used_percentage` from the context window. Only suggest clearing if above 60%. The plan is on disk — clearing is safe but not always necessary.
>
> **If above 60%:** "Context is at N%. Recommend clearing before execution: `/clear` then `/coding-team continue`"
> **If below 60%:** Do NOT suggest clearing. Just proceed.
>
> **During execution:** If you hit a bug that requires investigation, `/scope-lock` will lock edits to the affected directory so debugging can't accidentally change unrelated code. `/debug` auto-suggests this.
>
> ---

**User override:** If the user has said "never ask about second opinion" or "skip second-opinion gates" in this session, skip step 3 entirely for the rest of the session.
