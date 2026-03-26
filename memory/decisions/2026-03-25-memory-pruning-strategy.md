# Decision: Prune Promoted Rules from Memory

**Date:** 2026-03-25
**Context:** consolidated-feedback.md had 27 behavioral rules accumulated over a week of harness engineering. 12 of them had been promoted to structural enforcement (hooks, rule files, CLAUDE.md identity framing) but were never removed from the memory file.
**Decision:** Remove rules from consolidated-feedback.md once they have hook-level, rule-level, or identity enforcement. Keep only rules that exist at the prompt level with no structural backup.
**Rationale:** Redundant rules waste the orchestrator's attention budget (Case 24 — context saturation). Every line in a loaded file competes for attention. A rule already enforced by a hook adds no value in the memory file — the hook fires regardless. Pruning from 27 to 15 rules frees attention for the 30 case study principles that were added.
**Consequences:** 12 rules removed, 15 kept. The pruned rules are still documented in their individual feedback-*.md files for history. Future promotions (feedback → hook/rule) should include removing the rule from consolidated-feedback.md as the final step.
