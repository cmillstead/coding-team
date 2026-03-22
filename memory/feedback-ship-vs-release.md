---
name: Suggest /release not /ship
description: Coding-team must suggest its own /release skill, never gstack's /ship, for deploying and creating PRs
type: feedback
---

Always suggest `/release` (coding-team's own skill) instead of `/ship` (gstack) when the user is ready to deploy or create a PR.

**Why:** gstack's proactive suggestions table in the system prompt says "Ready to deploy → suggest /ship". This overrides the quieter `/release` references in coding-team's execution.md and completion.md. Same pattern applies to `/retrospective` vs `/retro` and `/doc-sync` vs `/document-release`.

**How to apply:** When suggesting next steps after execution or at any shipping point, explicitly name `/release` — never `/ship`. The coding-team equivalents are purpose-built for the coding-team pipeline and include the right verification gates.
