# Phase 1: Dialogue (Main Claude)

1. Read project context — files, docs, recent commits, CLAUDE.md
2. Ask clarifying questions **one at a time** — multiple choice preferred, open-ended when needed
3. If upcoming questions involve visual content (mockups, layouts, diagrams), offer the visual companion as its own standalone message before continuing questions
4. Propose 2-3 approaches with trade-offs and your recommendation. Structure:
   - At least one **minimal viable** approach (fewest files, smallest diff)
   - At least one **ideal architecture** approach (best long-term trajectory)
   - For complex features, add a **dream state** sketch: current state → this plan → 12-month ideal
5. Get user approval on direction

Do NOT create the Team Leader until the user has approved an approach.

**Scope check:** If the request describes multiple independent subsystems, flag this immediately. Help decompose into sub-projects before detailed design. Each sub-project gets its own design -> plan -> execution cycle.
