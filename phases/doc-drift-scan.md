## Documentation Drift Scan (after all tasks)

After plan completeness verification passes, check for documentation drift across the full diff before returning to `execution.md` (see Final step below).

**Tier gate:** SKIP this scan ONLY when the EFFECTIVE tier (from the single
end-of-execution recompute in `phases/task-weight.md`) is Trivial. Small/Medium/Large
RUN the doc-drift scan — do NOT skip for Small. Gate matrix: `phases/task-weight.md`.

**No-doc-impact early-exits (orthogonal to tier — apply at ANY tier when there is
provably nothing to scan):** These are NOT tier-based; they fire only when the diff
demonstrably has no documentation surface to check, which is legitimate at any tier.
Skip the scan (regardless of tier) when ANY of these hold:
- The feature only modified test files (no behavior change to document)
- Every implementer reported "No doc impact" for all tasks
- The plan explicitly noted "no documentation surface" in the NOT in scope section

**When NOT skipping:**

1. **Pre-filter doc files that reference changed code:**
   ```bash
   REPO_ROOT=$(git rev-parse --show-toplevel)
   CHANGED=$(git diff $(git merge-base HEAD main) --name-only)
   DOC_FILES=$(find "$REPO_ROOT" -maxdepth 3 -name "*.md" -not -path "*/.git/*" -not -path "*/node_modules/*")
   # Find doc files that mention any changed file stem
   echo "$CHANGED" | sed 's|.*/||; s|\.[^.]*$||' | sort -u | while read stem; do
     grep -l "$stem" $DOC_FILES 2>/dev/null
   done | sort -u
   ```

2. **Dispatch a doc-review agent via Agent tool (read-only Explore):**

   Pass the agent: the pre-filtered doc files list AND the actual diff summary (`git diff $(git merge-base HEAD main) --stat` plus key changes).

   Agent prompt:
   > Review these documentation files against the branch changes.
   >
   > Changed files with summary: [diff stat + key changes]
   > Doc files that reference changed code: [pre-filtered list]
   >
   > For each doc file, identify:
   > - Stale file paths (references to renamed, moved, or deleted files)
   > - Stale descriptions (behavior changed but docs describe the old way)
   > - Missing entries (new files, features, or APIs not yet documented)
   >
   > Report format:
   > - MUST_FIX: [doc file]: [what's stale] → [what it should say]
   > - NICE_TO_HAVE: [doc file]: [minor improvement]
   > - Or: "No drift detected"
   >
   > Do NOT make changes. Report only.

3. **If MUST_FIX findings:** dispatch an implementer via Agent tool to fix the doc issues as a single task.

4. **If only NICE_TO_HAVE or no drift:** continue. Note NICE_TO_HAVE items in the completion summary for `/doc-sync` to pick up.

**Final step — return to `execution.md`.** The scan is complete; continue from the point that invoked this scan (`execution.md:188`) and carry on through the rest of Phase 5. Do not re-read `execution.md` from the top and do not re-enter Phase 5 — the tier recompute and QA review above `:188` have already run for this feature.
