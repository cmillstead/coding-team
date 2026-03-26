# Decision: Audit Context Inheritance as Agent × File Matrix

**Date:** 2026-03-25
**Context:** Case 5 documented that implementers didn't receive code-style.md and design team leaders didn't receive golden-principles.md. The context was correctly passed at some boundaries but not others.
**Decision:** Context inheritance must be audited as a matrix: agents on one axis, reference files on the other. Every cell must be checked. Added golden-principles.md and team-memory.md to implementer dispatch. Added code-style.md to design team dispatch.
**Rationale:** In a multi-phase workflow with specialist agents, it's easy to wire up task-specific context (the plan, the diff) and forget shared reference context (style guides, principles, memory). The matrix makes gaps visible — an empty cell where a code-touching agent doesn't receive the style guide is obviously wrong.
**Consequences:** execution.md and design-team.md updated with additional context passing. The retro action items include creating a formal context inheritance matrix as a reference document.
