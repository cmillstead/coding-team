---
name: retrospective
description: "Use after shipping a feature or after a difficult debug session for an engineering retrospective. Analyzes commit history, work patterns, audit findings, and code quality. Produces a structured retro with what went well, what to improve, and recurring patterns."
---

# /retrospective — Engineering Retrospective

Post-ship analysis of what happened during the feature build. Looks at commit patterns, test health, audit findings, and process efficiency.

## When to Use

- After Phase 6 completion — review what just shipped
- End of sprint or work week — broader retrospective
- After a difficult debug session — capture lessons

## Workflow

1. **Gather data:**
   ```bash
   # Recent commits on this branch
   git log main..HEAD --oneline --stat

   # Commit frequency pattern
   git log main..HEAD --format="%ai" | cut -d' ' -f1 | sort | uniq -c

   # Files most frequently changed
   git log main..HEAD --name-only --format="" | sort | uniq -c | sort -rn | head -20
   ```

2. **Analyze patterns:**
   - **Commit hygiene:** Are commits atomic (one concern per commit)? Are messages descriptive?
   - **Test coverage:** Did every feature commit include tests? Any commits that only fix tests?
   - **Audit findings:** If a completion summary exists, extract recurring patterns.
   - **Rework:** How many fix/fixup commits? High rework suggests plan gaps.
   - **Velocity:** How many tasks completed per session? Where did time concentrate?

3. **Produce structured retro:**

```
## Retrospective: <feature name>

### What went well
- [specific positive observations with evidence]

### What to improve
- [specific actionable improvements]

### Recurring patterns
- [patterns from audit findings that appeared across multiple tasks]

### Metrics
- Commits: N total (N feature, N fix, N test, N docs)
- Files changed: N
- Rework ratio: N fix commits / N total commits
- Test commits: N / N feature commits

### Action items
- [ ] [concrete next step]
```

4. **Save retro to disk:**
   - Determine `$REPO_ROOT` via `git rev-parse --show-toplevel`.
   - Create directory `$REPO_ROOT/docs/retros/` if it does not exist using Bash tool: `mkdir -p "$REPO_ROOT/docs/retros/"`.
   - Write the structured retro from step 3 to `$REPO_ROOT/docs/retros/YYYY-MM-DD-<feature-slug>.md` using the Write tool. Use today's date and a kebab-case slug of the feature name.
   - If a completion summary exists from Phase 6, append it to the retro file as a `### Completion Summary` section using the Edit tool. Do NOT overwrite the retro content — append only.

5. **Eval feed-forward:**
   - Review the "What to improve" and "Recurring patterns" sections from the retro.
   - For each item that represents a check agents should have caught during implementation or audit (e.g., "missed null check pattern", "forgot to update schema after migration"), append it to `$REPO_ROOT/docs/project-evals.md` as a checklist item.
   - If `$REPO_ROOT/docs/project-evals.md` does not exist, create it using the Write tool with this exact template:

     ```markdown
     # Project-Specific Eval Criteria

     > Accumulated from retrospectives and debug sessions. The planning worker loads these as seed criteria for auditors.
     > Each item is a check that agents missed in a prior session.

     - [ ] [criterion]
     ```

   - Before appending, read the existing file and check for duplicates. Do NOT add a criterion that is already present (same meaning, even if worded differently). If all items are duplicates, skip this step.
   - Do NOT add generic criteria like "write better tests" — only add items that encode a specific check an agent could mechanically verify.

6. **Decision capture prompt:**
   - Ask the user: "Were any architectural or design decisions made during this feature that should be recorded? If yes, I'll save them as decision logs."
   - If the user provides decisions, write each to `$REPO_ROOT/docs/decisions/YYYY-MM-DD-<slug>.md` using the Write tool.
   - If the user says no or skips, proceed. Do NOT generate decisions the user did not identify.

## Red Flags

- Do NOT fabricate metrics — only report what git log shows
- Do NOT blame — focus on process, not people
- Do NOT skip if the feature was small — even small features have lessons
