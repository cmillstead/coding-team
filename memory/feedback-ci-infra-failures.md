---
name: CI infra/billing failures misdiagnosed as code issues
description: Agents waste cycles attempting code fixes for non-code CI failures (billing, permissions, runner quota)
type: feedback
---

Agents fail to read and classify CI failure logs. When CI fails due to infra/billing/permissions issues (GitHub Actions minutes exceeded, runner quota, permission denied), agents either ignore the failure or attempt code fixes that cannot resolve the problem.

**Why:** The CI fix instructions were a single vague paragraph ("diagnose the failure, dispatch an implementer to fix") with no failure classification. Agents defaulted to "fix code" for every CI failure because that was the only action path described.

**How to apply:** The CI Fix Protocol in `phases/completion.md` now requires reading the full log and classifying the failure type BEFORE taking action. Non-code failures (infra/billing/permissions) route to immediate user notification, not implementer dispatch. Code failures route to implementers with verbatim error context.
