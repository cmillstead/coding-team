# Phase 4: Planning Worker

Create a **Planning Worker task** with: design doc + full project context.

Worker is Architect + Senior Coder. Produces implementation plan.

## Step 0: Scope Challenge (before planning)

Before writing tasks, the planning worker must answer:

1. **What existing code already solves sub-problems?** Can we reuse rather than rebuild?
2. **What is the minimum set of changes?** Flag work that could be deferred without blocking the core goal.
3. **Complexity smell:** If the plan touches 8+ files or introduces 2+ new classes/services, challenge whether the same goal can be achieved with fewer moving parts.

## Plan Document Format

Every plan starts with this header:

```markdown
# [Feature Name] Implementation Plan

**Goal:** [One sentence describing what this builds]

**Architecture:** [2-3 sentences about approach]

**Tech Stack:** [Key technologies/libraries]

---
```

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

## Plan Review Loop

After writing the plan:

1. Dispatch plan-document-reviewer agent (see `prompts/plan-doc-reviewer.md`)
2. If Issues Found: fix, re-dispatch (max 3 iterations, then surface to user)
3. If Approved: save plan and proceed

Save plan to: `docs/plans/YYYY-MM-DD-<feature>.md` (always in the **main repo root**, not a worktree)

---

## Next Steps

After the plan passes review and is saved, print this block VERBATIM (substitute the actual plan path):

> ---
>
> **Plan saved to `docs/plans/<actual-path>`.**
>
> **Next:** Phase 5 execution. "Proceed to Phase 5"
>
> **Recommended before execution:**
> - `/codex review` — get a Codex second opinion on the plan (iterative — Codex reviews, Claude revises, up to 5 rounds)
> - `/worktree` — set up an isolated workspace (offered automatically)
>
> **Context check:** Phase 5 typically uses 60-80% of the context window. Clearing here preserves capacity for execution. The plan is on disk.
>
> **Clear and resume:** `/clear` then `/coding-team continue`
>
> **During execution:** If you hit a bug that requires investigation, `/freeze` will lock edits to the affected directory so debugging can't accidentally change unrelated code. `/debug` auto-suggests this.
>
> ---
