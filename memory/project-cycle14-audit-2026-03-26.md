---
name: Cycle 14 harness audit
description: Deploy drift critical (suppression.py missing), ENFORCEMENT_MAP 13→24, context survival gates, codex CLI syntax fix, spec-clarity rationalization
type: project
---

PR #35 merged. Three user-reported issues diagnosed via /prompt-craft, then cycle 14 harness audit found 9 findings (7 fixed, 1 deferred, 1 accepted).

**User-reported issues:**
1. Codex review CLI syntax — `--base` and `[PROMPT]` are mutually exclusive
2. QA review + second-opinion gates lost to context pressure in 45-task sessions
3. Orchestrator offers self-execution when "spec is already clear"

**Harness audit findings:**
- P1: Deploy drift — 10 hooks, `_lib/suppression.py`, 5 agents, ct-qa-reviewer all out of sync. 3 hooks would crash (missing import).
- P2: ENFORCEMENT_MAP had 13 entries, expanded to 24 — 11 feedback items were enforced but not mapped
- P2: 2 rules files (mcp-resilience, multi-pass-audit) existed only deployed, not in repo
- P2: 4 instruction files over 200 lines (deferred — needs dedicated session)
- P3: Fragile line-number reference replaced with section heading

**Why:** Deploy drift accumulated because `deploy.sh` wasn't run after cycle 13 commits. The suppression module (`_lib/suppression.py`) was never deployed — any hook importing it would crash silently.

**How to apply:** Run `deploy.sh` after every PR merge, not just after hook changes. The deploy drift class is the most persistent failure mode — it recurs every 2-3 cycles.
