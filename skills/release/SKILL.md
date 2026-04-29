---
name: release
description: "Push and create PR from within the coding-team pipeline — syncs branch, runs tests, reviews diff, pushes, creates PR, and optionally merges. Does NOT version bump or update CHANGELOG. For full ship with version bump and CHANGELOG, use /ship instead."
---

# /release — Automated Release Workflow

Ship the current branch with full verification. More thorough than the manual Phase 6 PR flow.

## Entry Point

If the user says "merge", "land it", or "merge and clean up" and a PR already exists for this branch:
1. Detect the PR: `gh pr view --json number,state -q '.number'`
2. Skip to step 7 (CI verification) → step 8 (merge).

If no PR exists, start from step 1.

## Workflow

1. **Detect base branch:**
   ```bash
   BASE=$(gh pr view --json baseRefName -q .baseRefName 2>/dev/null || gh repo view --json defaultBranchRef -q .defaultBranchRef.name 2>/dev/null || echo "main")
   ```

2. **Sync base branch:**
   ```bash
   git fetch origin "$BASE"
   git merge "origin/$BASE" --no-edit
   ```
   If merge conflicts: stop and report. Do NOT force-resolve.

3. **Run full test suite:**
   ```bash
   # Detect and run the project's test command
   ```
   If tests fail: stop and report. Do NOT proceed with failing tests.

4. **Run linter:**
   ```bash
   # Detect and run the project's lint command
   ```
   If lint errors: fix trivially fixable ones, re-run, confirm clean.

4b. **Second-opinion gate (active plan only):**
    Detect the active plan file (most recent in-progress plan in `docs/plans/`, modified within the last 4 hours):
    ```bash
    MAIN_ROOT=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null | sed 's|/.git$||')
    [ -d "$MAIN_ROOT/docs/plans" ] && \
      ACTIVE_PLAN=$(find "$MAIN_ROOT/docs/plans" -maxdepth 1 -name '*.md' -mmin -240 -print0 2>/dev/null | \
        xargs -0 ls -t 2>/dev/null | \
        while read -r p; do
          head -20 "$p" | grep -qE '^status:\s*complete' || { echo "$p"; break; }
        done) || ACTIVE_PLAN=
    ```
    - If `ACTIVE_PLAN` is empty (no recent in-progress plan — standalone `/release`): skip this step, continue to step 5.
    - If `ACTIVE_PLAN` is set, check the Completion Checklist for the Second-opinion review line:
      ```bash
      grep -E '^- \[[ x]\] Second-opinion review' "$ACTIVE_PLAN"
      ```
      - If the matched line is `- [x]` OR contains `skip:` → gate satisfied, continue to step 5.
      - If the matched line is `- [ ]` and does NOT contain `skip:`:
        Print: "Second-opinion gate not completed. Active plan: $ACTIVE_PLAN. Run `/second-opinion review` before shipping, or edit the plan to mark `- [x] Second-opinion review (skip: <reason>)` and try `/release` again."
        STOP and wait for user response. Do NOT proceed to push.
      - If no `Second-opinion review` line is present in the plan (back-compat with older plans): gate satisfied, continue to step 5.

5. **Review diff:**
   ```bash
   git diff "$BASE"...HEAD --stat
   git log "$BASE"..HEAD --oneline
   ```
   Summarize: N files changed, M commits, key changes.

6. **Push and create PR:**
   ```bash
   git push -u origin HEAD
   gh pr create --title "<title>" --body "<summary with test plan>"
   ```

7. **Wait for CI and verify:**
   ```bash
   PR_NUM=$(gh pr view --json number -q .number)
   gh pr checks "$PR_NUM" --watch --fail-fast
   ```
   - **All checks pass:** Report PR URL and summary. Done.
   - **Any check fails:** Follow the **CI Fix Protocol** in `phases/completion.md`.
     Read that protocol, classify the failure, and act accordingly.
     Key rules: read full logs, classify before acting, NEVER fix infra/billing issues with code changes, paste verbatim errors to implementers.
     Do NOT invoke `/coding-team` from within `/release` (recursive invocation).
   - **After pushing a CI fix:** re-run `gh pr checks "$PR_NUM" --watch --fail-fast` to verify the fix. Do NOT declare success until CI passes. If the fix introduced NEW failures, this counts toward the 3-attempt cap. After 3 total failed fix attempts, close the PR (`gh pr close "$PR_NUM" --delete-branch`) and report to user.

8. **Merge:**
   Merge only when: (a) CI passed in step 7, or (b) no CI checks configured, or (c) user explicitly says "merge" after seeing CI status.
   ```bash
   PR_NUM=$(gh pr view --json number -q .number)
   gh pr merge "$PR_NUM" --merge --delete-branch
   ```
   After merge, switch to base branch and pull:
   ```bash
   git checkout "$BASE" && git pull origin "$BASE"
   ```
   Report: "Merged PR #N into $BASE. Branch deleted."

   **Do NOT auto-merge.** Step 8 only runs when the user explicitly requests merge. After step 7 succeeds, report the PR URL and wait. The user decides when to merge.

## When to Use

- After Phase 5 execution completes — as an alternative to manual Phase 6
- After Phase 6 when user chose "Push and create PR" but wants more automation
- Anytime the user says "ship it", "create a PR", "release this"
- When the user says "merge", "land it", "merge and clean up"
- After CI passes on a PR created by /release

## When NOT to Use

- If tests are failing — fix first
- If on the base branch (main/master) — need a feature branch
- If there are uncommitted changes — commit first

## Red Flags

- NEVER push to main/master directly
- NEVER create a PR with failing tests
- NEVER force-push without explicit user consent
- ALWAYS include a test plan in the PR body
- NEVER fix CI failures directly in the orchestrator — dispatch an implementer via Agent tool. Do NOT invoke `/coding-team` from within `/release` (recursive invocation).
- NEVER leave a PR with failing CI without explicit user choice — close it after 3 failed fix attempts
- NEVER attempt code fixes for infra/billing/permissions CI failures — report to user immediately
- NEVER merge a PR with failing CI unless the user explicitly overrides
- NEVER auto-merge after CI passes — always wait for user to say "merge"
