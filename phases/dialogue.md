# Phase 1: Dialogue (Main Claude)

**Tier gate (see `phases/task-weight.md` gate matrix):**
- **Trivial/Small fully-specified request: SKIP Phase 1 entirely** — per the ladder, not per mood. Do NOT run the question→approach→approval cycle; do NOT create the Team Leader; proceed directly to Phase 4 (planning). The approach is already specified.
- **Medium/Large request: RUN the full Phase 1 cycle below.**

1. Read project context — files, docs, recent commits, CLAUDE.md. **Tier scope: Medium/Large only.** Trivial/Small SKIP the context re-read and go directly to planning.
2. Ask clarifying questions **one at a time** — multiple choice preferred, open-ended when needed
3. If upcoming questions involve visual content (mockups, layouts, diagrams), offer the visual companion as its own standalone message before continuing questions
4. Propose approaches with trade-offs and your recommendation. **Approach count is tier-scoped:**
   - **Trivial/Small:** propose 1 approach when only one is sensible — do NOT manufacture alternatives.
   - **Medium/Large:** propose 2-3 approaches. Structure:
     - At least one **minimal viable** approach (fewest files, smallest diff)
     - At least one **ideal architecture** approach (best long-term trajectory)
     - For complex features, add a **dream state** sketch: current state → this plan → 12-month ideal
5. Get user approval on direction

**Do NOT create the Team Leader until the user has approved an approach.** Exception: Trivial/Small tasks with a fully-specified approach SKIP approval and go directly to Phase 4 — the approach is already specified.

**Scope check:** If the request describes multiple independent subsystems, flag this immediately. Help decompose into sub-projects before detailed design. Each sub-project gets its own design -> plan -> execution cycle.

---

## Next Steps

After the user approves an approach, print this block VERBATIM (do not paraphrase, reorder, or omit lines). Substitute actual feature name where applicable:

> ---
>
> **Approach approved.**
>
> **Continue now:** "Proceed to Phase 2"
>
> [Only if context `used_percentage` is above 60%:]
> **Context at N%.** Clear first: `/clear` then `/coding-team continue`
>
> **After Phase 2:** You'll review a design doc, then optionally run `/second-opinion consult` for an independent architecture perspective before proceeding to planning.
>
> **If this task involves prompt or skill changes:** The Prompt/Skill Specialist will be included in the design team. You can also run `/prompt-craft audit` on any existing skills before proceeding.
>
> **If this task involves review feedback:** Use `/review-feedback` to evaluate the feedback technically before designing a solution.
>
> ---

**If the user rejects all approaches** or says 'never mind': acknowledge, do NOT proceed to Phase 2. Ask if they want to explore a different direction or end the task.
