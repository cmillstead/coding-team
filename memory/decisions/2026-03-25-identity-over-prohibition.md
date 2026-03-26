# Decision: Identity Framing Over Prohibition for Delegation

**Date:** 2026-03-25
**Context:** After 7 rounds of the Delegation War (Cases 1→3→4→7→16→19→28), escalating prohibition language ("NEVER", "STOP", "No exceptions") reached 20+ lines in CLAUDE.md and produced grumpy compliance — the agent narrated constraints instead of internalizing them.
**Decision:** Replace prohibition stack with identity framing: "You are the engineering manager. Your team writes code." Reserve prohibition for safety rails only (secrets, force-push, deployed migrations).
**Rationale:** An agent told "you are a manager" doesn't try to write code because managers don't write code. An agent told "you MUST NOT write code" will always look for exceptions. Identity framing eliminates the tension that produces escape hatches. Validated over 4 days with zero delegation bypasses since the switch (feedback-strategy-validation.md).
**Consequences:** All agent prompts now lead with identity statements. The identity-framing-check.py hook enforces this on new files. The CLAUDE.md delegation section dropped from 20+ lines to 7.
