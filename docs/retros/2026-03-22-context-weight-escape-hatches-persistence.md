## Retrospective: Context Weight Refactor + Escape Hatch Hardening + Institutional Knowledge Persistence

### What went well
- **Parallel execution worked cleanly.** All parallel agent dispatches (3 tasks for context weight, 5 for audit fixes, 4 for institutional knowledge) completed without conflicts. File-per-task decomposition eliminates merge conflicts entirely.
- **Case study-driven audit was thorough.** Reading the 19-case ebook then auditing against every pattern found 7 new issues that ad-hoc review would have missed. The pattern taxonomy gives a structured search space.
- **Live bug discovery fed forward immediately.** Case 19 (recursive invocation) was discovered during execution and fixed in the same PR — didn't need a separate session.
- **Escape hatch diagnosis was fast.** "Only warnings" and "CI orphan" issues were diagnosed and fixed within minutes of being reported — the `/prompt-craft diagnose` flow is effective.
- **Three features shipped in one session** — context weight refactor (plan existed), escape hatch hardening (audit-driven), institutional knowledge persistence (spec existed). Session handled multiple workflows smoothly.

### What to improve
- **Cross-layer propagation still requires manual checking.** Case 19 was fixed in implementer.md but not initially propagated to harden auditor, Team Leader, or Planning Worker. The audit caught it, but a systematic "grep all agent prompts for the same gap" step would catch it during the fix, not after.
- **README line counts go stale immediately.** Updated them in `/doc-sync` but they'll drift again with the next change. Consider removing line counts from README entirely — they serve no behavioral purpose and create maintenance burden.
- **Plan file accumulation.** 8 plan files in `docs/plans/`, most completed. No archival or cleanup mechanism — will get noisy over time.

### Recurring patterns
- **Identity statements are needed everywhere agents use Edit/Write/Bash.** Every agent that can write code needs the "you are INSIDE the pipeline" override. This came up 4 times in this session.
- **Named rationalizations are the most reliable fix.** "Pre-existing," "only warnings," "test expectations" — naming the agent's bypass phrase and turning it into a compliance trigger works every time.
- **Extracted files need navigation hints.** When splitting content from parent to child file, always add a preamble (where loaded from) and a return instruction (where to go next).

### Metrics
- Commits: 17 total across session (12 in PR #1 pre-squash, 1 doc-sync, 4 in PR #2)
- Files changed: 16 unique files across both PRs
- Feature commits: 8, Fix commits: 8, Docs commits: 2
- Rework ratio: 0 fix-of-fix commits / 17 total
- Test commits: 0 / 8 feature (no test suite — markdown instruction files)

### Action items
- [ ] Consider removing line counts from README — they drift and serve no purpose
- [ ] Add "grep all agent prompts" step to the fix propagation workflow
- [ ] Archive completed plan files (or add a completed/active marker)
