# Decision: Dual-Agent Audits (Harness + Prompt-Craft)

**Date:** 2026-03-25
**Context:** Single-agent audits (just harness-engineer or just prompt-craft) miss classes of issues. Harness-engineer finds structural gaps (hooks, settings, constraint coverage). Prompt-craft finds instruction quality gaps (YAML ordering, missing sections, framing issues).
**Decision:** For comprehensive harness audits, always dispatch both agents in parallel against the same checklist. The harness-engineer checks infrastructure. The prompt-craft auditor checks instruction text. Merge findings, dedupe, prioritize.
**Rationale:** This session's dual audit found 8 gaps. The harness agent found the P1 router hook escape hatch and the missing same-class search. The prompt-craft agent found the YAML tool ordering issue and the structure-test detection gap. Neither alone would have found all 8.
**Consequences:** The /harness-engineer skill description should note that for full audits, it pairs with /prompt-craft. The harness-audit-cycle5 project memory already documents this pattern from the sixth audit cycle.
