---
name: Exit gate colocation
description: Mandatory post-execution gates (QA, second-opinion, doc-drift) were skipped because they lived in late-loaded files behind read indirection; fixed by inlining into SKILL.md exit gate
type: feedback
---

Post-execution gates (full-suite verification, feature-level QA, doc-drift scan, second-opinion) were consistently skipped — especially for small executions (1-2 tasks) that never hit the 3-task mid-phase reminder cadence.

**Why:** Three compounding causes from ebook case studies:
- **Structural demotion (Case 9)** — gates at line 204 of a 204-line file are treated as optional
- **Propagation failure (Case 18)** — execution.md → read execution-reminders.md → read post-execution-review.md = 3 hops, each lossy
- **Context pressure** — after implementer + auditor dispatch, the back half of execution.md gets compacted first

**How to apply:** Mandatory gates must live in SKILL.md's Phase Sequence section (always in context, never compacted) — not in late-loaded detail files. Detail files remain as reference for the full procedure, but the gate checklist itself is inlined. This applies to any future mandatory gate: if it must not be skipped, it belongs in SKILL.md, not behind a "read file X" instruction.
