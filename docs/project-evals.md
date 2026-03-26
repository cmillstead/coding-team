# Project-Specific Eval Criteria

> Accumulated from retrospectives and debug sessions. The planning worker loads these as seed criteria for auditors.
> Each item is a check that agents missed in a prior session.

- [ ] When fixing a behavioral rule in one agent prompt (e.g., implementer.md), grep ALL other agent prompts (auditors, Team Leader, Planning Worker) for the same gap before reporting DONE — added 2026-03-22 from retro: context-weight-escape-hatches
- [ ] When extracting content from a parent file to a child file, verify the child has a navigation preamble (where it's loaded from) and a return instruction (where to go next) — added 2026-03-22 from retro: context-weight-escape-hatches
- [ ] When editing CC instruction files, verify no "skip/directly/simple" language grants unscoped bypass exemptions — added 2026-03-25 from retro: case-study-audit (Case 28 recurrence)
- [ ] After fixing a security finding, search all analogous call sites for the same vulnerability class — added 2026-03-25 from retro: case-study-audit (Case 23)
- [ ] When multiple tasks touch the same file, verify edits don't contradict each other — added 2026-03-25 from retro: case-study-audit (3 agents on ct-harden-auditor.md)
