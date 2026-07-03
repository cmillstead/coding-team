---
name: Pipeline friction audit session
description: Two structural gates shipped (second-opinion, lint exit code spec), full friction audit specced, gstack auto-codex pattern identified
type: project
---

Session on 2026-03-27 analyzed pipeline friction from behavioral incidents and produced three deliverables.

**Shipped:**
1. Second-opinion structural gate in lifecycle hook (PR #49) — PostToolUse blocks completion unless `/tmp/second-opinion-completed` or `/tmp/second-opinion-declined` exists. Fail-closed. 25/25 tests.

**Specced (ready for /coding-team):**
2. Lint exit code verification in git-safety-guard — `docs/plans/2026-03-27-lint-exit-code-gate-design.md`. PostToolUse captures exit codes, PreToolUse commit gate checks they passed. Escalates to user, doesn't force-fix.
3. Full pipeline friction audit — `docs/plans/2026-03-27-pipeline-friction-audit-design.md`. 4-pass audit: gate inventory, gstack comparison, ebook principle application, prioritized fix plan.

**Key findings:**
- 32 documented gates, only 8 structurally enforced (25%)
- gstack auto-runs codex in `/ship` scaled by diff size — no user prompting. Coding-team should adopt this pattern in `/release`.
- The "pre-existing" rationalization has a variant: "zero errors in our changed files" — lint scope narrowing. Named in feedback memory.
- Adding more documentation to paper gates doesn't work. The second-opinion gate was in 7 files and still got skipped every session.

**How to apply:** Run `/coding-team continue the pipeline friction audit` in a fresh conversation. Spec includes lint exit code gate + auto-codex in release + holistic gate evaluation.
