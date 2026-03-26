---
name: Hook accumulation from harness-engineer audit cycles
description: Harness-engineer's Promotion Flywheel frames every feedback memory as a hook candidate, causing 44% hook growth in 5 cycles; root cause is framing bias in agent instructions
type: feedback
---

Harness-engineer recommends new hooks every audit cycle (1-2 per cycle). Over 5 cycles, hooks grew from 16→23. Root cause: the agent's instructions have a structural bias toward hook creation with no counter-pressure.

**Why (prompt-craft diagnosis):**
1. Line 135: "Every feedback memory is a promotion candidate" — frames non-promotion as a gap
2. Verb priority ladder (Constrain > Inform) — hooks always rank higher than rules/instructions
3. The only throttle (3-session stability check) is in the reference file, not at the decision point
4. No cost model — hook count, per-call overhead, consolidation opportunities never evaluated
5. Hook Design Protocol jumps to "design the hook" without "check if an existing hook can absorb this"

**How to apply:** The ct-harness-engineer agent needs these fixes:
1. **Identity reframing**: harness engineer is a *steward* of hook health, not just a promoter. Stewards resist bloat.
2. **Pre-creation gate** at audit step 3: before recommending any new hook, check (a) can an existing hook absorb it via _lib/? (b) is a rule or instruction sufficient? (c) has the prompt-level fix actually failed, or is it holding?
3. **Cost awareness**: SessionStart hooks are cheap (fire once). PreToolUse/PostToolUse hooks compound on every tool call. Above 18 hooks, any new per-call hook must justify itself against "just put it in the instruction file."
4. **Named rationalization**: "this failure needs structural enforcement" — not every failure needs a hook; stable prompt-level fixes are fine.
5. **Move the 3-session gate inline** at the promotion decision point (line 135), not buried in the reference file.
