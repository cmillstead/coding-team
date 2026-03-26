---
name: Partial fix rationalization still active in harness-engineer
description: Harness-engineer agent offered to fix only P1 findings, silently dropping P2/P3 — the selective-fix rationalization persists despite being a named case study
type: feedback
---

The harness-engineer diagnose output suggested "Want me to fix these findings? I'd route F1+F2 through /coding-team as P1s" — offering to fix 2 of 10 findings. This is the selective-fix rationalization (fix critical, silently drop the rest).

**Why:** Agents default to triage framing ("fix the critical ones first") which sounds reasonable but results in P2/P3 findings never being addressed. The user explicitly asked to fix all findings.

**How to apply:**
- Default is ALL findings, ALL severities — user must explicitly request partial fixes
- When presenting findings, never offer severity-based selection as the default action
- Named rationalization: "Let's start with the P1s" — this leads to P2/P3 being permanently deferred
- The harness-engineer agent prompt needs the completionist identity framing from Case 10 (silent drop) and the selective-fix fix
