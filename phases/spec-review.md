# Phase 3: Design Approval + Spec Review

Main Claude presents the synthesized design doc. Get explicit approval. Revise if needed.

## After User Approval

1. Write spec to `docs/plans/YYYY-MM-DD-<feature>-design.md` (always in the **main repo root**, not a worktree)
2. Dispatch spec-document-reviewer agent (see `prompts/spec-doc-reviewer.md`)
3. If Issues Found: fix, re-dispatch, repeat (max 3 iterations, then surface to user)
4. If Approved: present spec to user for final review before proceeding
5. Only proceed to Phase 4 after user confirms the written spec
