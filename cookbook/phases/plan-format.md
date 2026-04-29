# Plan Document Format

Reference material for the planning worker. Follow this format exactly when writing plan documents.

## Header

Every plan starts with YAML frontmatter and this header. The frontmatter `status` field is set to `planned` by the planning worker; the orchestrator flips it to `in-progress` at Phase 5 entry and `complete` at Phase 6 end (see `cookbook/phases/planning.md` "Plan status lifecycle" for the full state machine).

```markdown
---
status: planned
---

# [Feature Name] Implementation Plan

**Input findings: [N]** <- include ONLY when addressing scan/review findings; omit for feature work

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

**Side-effects:** [only include when task creates infrastructure artifacts]
- Hook registration in `settings.json`
- Symlink in `~/.claude/skills/` or `~/.claude/agents/`
- Deployment via `scripts/deploy.sh`
- Config update in `.mcp.json`, `package.json`, etc.

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

**Infrastructure tasks:** When a task creates hooks, agents, skills, or config files that require registration or deployment beyond the file itself, include a final step: "Register/deploy: [exact command or manual step]." Unregistered infrastructure is a dark feature — it exists but doesn't work.

## Model Assignment Per Task

The planning worker assigns a model tier to each task:
- **haiku** — touches 1-2 files with complete spec, mechanical changes
- **sonnet** — touches multiple files, needs judgment, integration work
- **opus** — requires design decisions, broad codebase understanding

## Testing Rules (baked into every plan)

- Never mock what you can use for real
- Only mock external systems genuinely unavailable in test environment
- Never mock the thing being tested
- Every task batch ends with: run tests -> run linter -> confirm both pass -> commit
- Every status/error mapping table must include a catch-all row ("all other cases -> ..."). Design specs that leave the "else" path undefined cause health() / observe() style bugs where unexpected inputs fall through to success paths.
