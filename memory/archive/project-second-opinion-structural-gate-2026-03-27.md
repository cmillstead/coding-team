---
name: Second-opinion structural gate
description: Promoted second-opinion from 7-file paper gate to structural Verify-verb hook in lifecycle hook; PR #49
type: project
---

Promoted second-opinion gate from documentation-only (7 files, zero enforcement) to structural hook enforcement in `coding-team-lifecycle.py`.

**Why:** Gate was skipped every session despite being documented in 7 files across 5 layers of indirection. Instruction-based enforcement degrades to ~0% compliance under context pressure. The KB diagnosed this (feedback-exit-gate-colocation, consolidated-feedback rule 39) but the prescribed Verify-verb fix was never built.

**How to apply:**
- Lifecycle hook PostToolUse blocks completion unless `/tmp/second-opinion-completed` or `/tmp/second-opinion-declined` exists
- Fail-closed: neither marker → block. The agent cannot rationalize past a structural block.
- Phase file escape hatch changed from verbal instruction to marker file — hook is the authority
- Pattern generalizable: any gate that matters needs structural enforcement, not more documentation

**Broader finding:** 32 documented gates in the pipeline, only 8 structurally enforced (25%). The pipeline assumes LLM compliance for phase transitions. Git operations are structurally gated; phase transitions are not. Future work: evaluate which other paper gates need promotion.

PR #49, merged into main.
