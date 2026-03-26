---
name: Harness audit cycle 11 results
description: Eleventh audit: 2 new Correct-verb hooks (config-drift-correction, test-gap-correction), PR-level cost aggregation, completionist identity in harness-engineer agent
type: project
---

Cycle 11 fixed 3 open findings from the diagnose + 1 agent prompt fix:

- **F7: Correct verb strengthened** — 2 new hooks: config-drift-correction.py (detects unregistered hooks = prevents dark features), test-gap-correction.py (detects missing test files = prevents test-coverage-attrition). Correct verb now at 4/20 hooks.
- **F8: PR-level cost aggregation** — metrics-analyzer.py enhanced with `aggregate_by_branch()` and `format_branch_summary()` for cumulative branch-level cost tracking. Key Level 4 metric.
- **F9: Codesight-mcp indexing** — coding-team repo indexed (42 files, 420 symbols).
- **Agent prompt fix** — ct-harness-engineer.md got completionist identity section with 3 named rationalizations preventing the partial-fix pattern.

**Why:** The diagnose showed Correct verb was weakest (2/18), no PR-level metrics, and the harness-engineer itself was suggesting partial fixes.

**How to apply:** Config-drift-correction and test-gap-correction are self-reinforcing — they'll catch future dark features and test gaps automatically. The completionist identity should prevent the harness-engineer from ever suggesting "fix P1s only" again.

Test count: 141 → 179 (38 new tests).
