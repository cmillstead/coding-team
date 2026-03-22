---
name: Agent teams vs subagents — use COORDINATION signal
description: Agent teams when agents need to talk to each other in real time; subagents when work is independent. COORDINATION is the dominant signal.
type: feedback
---

Use the three-signal heuristic (COORDINATION, DISCOVERY, COMPLEXITY) at every multi-agent dispatch point. COORDINATION is the dominant signal: will one agent's work affect another's in real time?

**Why:** First attempt framed agent teams as "the exception" — CC never used them. Second attempt made agent teams "the default for everything" — too blunt, used teams for independent work like audit dispatch. The right answer: agent teams for design (cross-domain coordination), subagents for execution (independent, pre-decomposed tasks).

**How to apply:**
- Design phase → agent teams (COORDINATION=yes: specialists' findings affect each other)
- Execution implementer → subagents (COORDINATION=no: one agent per task, distinct files)
- Execution audit → subagents (COORDINATION=no: read-only, report independently)
- Debugging 3+ hypotheses → agent teams (COORDINATION=yes: evidence can refute peers)
- Parallel fix shared infra → agent teams (COORDINATION=yes: cross-domain discovery)
- Single-agent tasks → always subagents (no multi-agent dispatch)
