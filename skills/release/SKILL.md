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
