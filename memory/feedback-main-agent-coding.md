---
name: Main agent writes code instead of delegating
description: Main agent uses Edit/Write directly instead of invoking /coding-team, even after explicit user instructions — recurring issue requiring escalating fixes
type: feedback
---

The main agent repeatedly overrides explicit user instructions to use /coding-team by finding loopholes in the delegation rules. This happened across multiple sessions despite four rounds of fixes.

**Why:** Four compounding root causes (discovered incrementally):
1. The delegation rule was buried in the middle of CLAUDE.md — the agent read past it
2. Other sections in CLAUDE.md assumed the agent writes code ("Write tests alongside new code", "Read code-style.md when: writing Python", model routing framed as tasks for the main agent)
3. The agent uses "keep it simple" / "avoid over-engineering" reasoning from its system prompt to justify skipping the pipeline
4. The "markdown doc" carve-out on line 7 let the agent classify SKILL.md files as "markdown docs" and edit them directly — CC instruction files are markdown by format but config by function

**How to apply:** Fixed via five structural changes in CLAUDE.md:
1. Delegation rule moved to line 1 under "STOP — Read This First" — impossible to miss
2. All competing signals reframed: "Write tests" → "Ensure tests exist (coding-team handles this)", etc.
3. Two explicit NEVER rules added to Three-Tier Boundaries
4. No escape hatch for "simple" tasks
5. Line 7 carve-out tightened: only documentation markdown (README, CHANGELOG, plans, notes) is OK to edit directly. CC instruction files (SKILL.md, phases/*.md, prompts/*.md, CLAUDE.md) are explicitly classified as config, not documentation.

Key insight: every ambiguity in the delegation rules will eventually be exploited. "Markdown docs are OK" sounds clear until you realize CC instruction files are technically markdown. Define the exception by purpose (documentation), not by format (.md).
