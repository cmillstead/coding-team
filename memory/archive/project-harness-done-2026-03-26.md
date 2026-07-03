---
name: Harness Definition of Done — Level 3 achieved
description: Harness declared Level 3 complete on 2026-03-26; moratorium on harness work until 2026-04-09; quarterly audit cadence going forward
type: project
---

Harness is at Level 3 (complete). All 7 acceptance criteria met on 2026-03-26. Cases 38-40 documented the infinite audit regress pattern that motivated this.

**Why:** 14 audit cycles in 5 days, 168 commits, 119 audit-related. Each fix created surface area for the next audit. The completionist identity + promotion flywheel + no definition of done = infinite loop. The harness became the product instead of the tool.

**How to apply:**
- **Moratorium**: No harness changes until 2026-04-09 unless production use reveals a breakage
- **Quarterly audits only**: One `/harness-engineer audit` per quarter, not per session
- **P1 only at maturity**: At Level 3+ with ≤20 hooks, only fix P1 findings (broken, security). P2/P3 are informational.
- **New hooks require pre-creation gate**: absorption check, sufficiency check, cost check (see feedback-hook-accumulation.md)
- **Use the harness to ship code** — that's what it was built for
