# CI Fix Protocol

> Loaded by the orchestrator from `cookbook/phases/completion.md` when CI fails after pushing. Return to completion.md after CI passes or after 3 failed attempts.

After pushing, watch CI:

```bash
PR_NUM=$(gh pr view --json number -q .number)
gh pr checks "$PR_NUM" --watch --fail-fast
```

**When a background CI watcher completes:** Read its output FIRST. Do NOT assume the result based on prior context. "Already handled" is not a valid dismissal — read the actual output, classify the result, then act. A watcher you launched 5 minutes ago may be reporting a new failure, not the one you think.

If all checks pass: report PR URL and summary. Done.

If CI fails:

### 1. Read the FULL failure log

```bash
gh pr checks "$PR_NUM"
gh run view --log-failed
```

Read the COMPLETE output. Do NOT skim or summarize.

### 2. Classify the failure

| Type | Signal keywords | Action |
|------|----------------|--------|
| Lint/format | "eslint", "prettier", "ruff", "clippy", "black" | Run linter locally, dispatch implementer to fix |
| Type check | "tsc", "mypy", "pyright", "type error" | Run type checker locally, dispatch implementer to fix |
| Test failure | "FAILED", "AssertionError", "FAIL:", test names | Run the specific failing test locally, dispatch implementer to debug |
| Build failure | "build failed", "compilation error", "Module not found" | Fix build locally, dispatch implementer |
| **Infra/billing** | "billing", "minutes exceeded", "rate limit", "quota", "no hosted runner", "usage limit", "402", "spending limit" | **STOP. Not a code problem. Report to user immediately with exact error.** |
| **Permissions** | "permission denied", "403", "Resource not accessible", "token expired" | **STOP. Not a code problem. Report to user immediately.** |
| Env/config | "not found" (for env vars), "version", "unsupported engine" | Check CI config vs local env, report difference to user |
| Unknown | None of the above match | Paste the FULL log output to the user and ask for guidance. Do NOT guess. |

**Non-code failures (infra/billing/permissions/unknown):** Present to user immediately:

> CI failed with a non-code error. This is not fixable by changing code.
>
> **Error type:** [infra/billing/permissions/unknown]
> **Full error:** [paste verbatim]
>
> Options:
> 1. Keep PR open (you handle the infra issue, then re-run CI)
> 2. Close PR and delete branch
> 3. Close PR, keep branch (re-open after fixing)

Do NOT attempt code fixes for non-code failures. Do NOT retry. Do NOT dispatch an implementer via Agent tool.

### 3. For code failures: dispatch implementer via Agent tool

Pass to the implementer (see `## CI Fix Context` in `~/.claude/agents/ct-builder.md`):
- Failing CI step name
- VERBATIM error output — paste the full log, not a summary
- Files and lines mentioned in the error
- What was already tried (if this is retry 2 or 3)

NEVER summarize CI errors — paste them verbatim to the implementer.
NEVER assume "it passed locally so the CI error is wrong."
NEVER fix CI failures directly as the orchestrator — dispatch an implementer via Agent tool.

### 4. After fix: re-push and re-watch

```bash
git push
gh pr checks "$PR_NUM" --watch --fail-fast
```

### 5. Max 3 code-fix attempts

If CI still fails after 3 fix attempts, present:

> CI still failing after 3 fix attempts. Options:
> 1. Close PR and delete branch (`gh pr close --delete-branch`)
> 2. Keep PR open (you handle it manually)
> 3. Let me try a different approach

Do NOT leave a failing-CI PR open without explicit user choice. If the user does not respond (session ending, context above 80%), close the PR and delete the branch: `gh pr close --delete-branch`. An orphan PR with failing CI generates email noise indefinitely.
