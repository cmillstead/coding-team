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

## Red Flags

- Do NOT fabricate metrics — only report what git log shows
- Do NOT blame — focus on process, not people
- Do NOT skip if the feature was small — even small features have lessons
