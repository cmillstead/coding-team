---
name: release
description: "Use when ready to ship code. Automated release workflow: sync base branch, run tests, review diff, push, create PR with summary and test plan. Use instead of manual Phase 6 completion for a more thorough automated flow."
---

# /release — Automated Release Workflow

Ship the current branch with full verification. More thorough than the manual Phase 6 PR flow.

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
   # Get the PR number from the URL
   PR_NUM=$(gh pr view --json number -q .number)
   # Wait for checks to complete (timeout 10 minutes)
   gh pr checks "$PR_NUM" --watch --fail-fast
   ```
   - **All checks pass:** Report PR URL and summary. Done.
   - **Any check fails:** Read the failure output:
     ```bash
     gh pr checks "$PR_NUM"
     gh run view --log-failed
     ```
     Diagnose the failure. Fix it via `/coding-team` (delegate — do NOT fix directly). After fix is pushed, re-run step 7.
     Do NOT leave a PR with failing CI. The release is not done until CI is green.

## When to Use

- After Phase 5 execution completes — as an alternative to manual Phase 6
- After Phase 6 when user chose "Push and create PR" but wants more automation
- Anytime the user says "ship it", "create a PR", "release this"

## When NOT to Use

- If tests are failing — fix first
- If on the base branch (main/master) — need a feature branch
- If there are uncommitted changes — commit first

## Red Flags

- NEVER push to main/master directly
- NEVER create a PR with failing tests
- NEVER force-push without explicit user consent
- ALWAYS include a test plan in the PR body
- NEVER fix CI failures directly — always delegate via `/coding-team`
