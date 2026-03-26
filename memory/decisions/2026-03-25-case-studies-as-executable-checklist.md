# Decision: Use Case Studies as Executable Audit Checklist

**Date:** 2026-03-25
**Context:** The harness-debugging-case-studies.md document (30 cases) was originally written as a historical record. During this session, we fed it into harness-engineer and prompt-craft agents as audit context.
**Decision:** Treat the 30 case studies as an executable checklist. Periodically (every 5-10 PRs) run dual-agent audits checking every case against current harness state. Also load all 30 principles into consolidated-feedback.md so the orchestrator has them in session memory.
**Rationale:** The first audit found 8 real gaps including a Case 28 recurrence in the router hook. The document catches recurrences at new locations that individual case fixes don't cover. It's the self-improving harness loop described in the case studies' meta-observation: more cases → better audits → fewer failures.
**Consequences:** consolidated-feedback.md now has 30 case study principles. SKILL.md tells the orchestrator to load it at session start. The retro action items include periodic re-audit.
