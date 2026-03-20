# Debugging Protocol

When a task fails during execution, follow this protocol instead of guessing.

## The Iron Law

```
NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST
```

If you haven't completed Phase 1, you cannot propose fixes.

## Phase 1: Root Cause Investigation

1. **Read error messages carefully** — don't skip past errors. Read stack traces completely. Note line numbers, file paths, error codes.

2. **Reproduce consistently** — can you trigger it reliably? What are the exact steps? If not reproducible, gather more data — don't guess.

3. **Check recent changes** — what changed that could cause this? Git diff, recent commits, new dependencies, config changes.

4. **Gather evidence in multi-component systems** — before proposing fixes, add diagnostic instrumentation at each component boundary. Run once to see WHERE it breaks, THEN analyze.

5. **Trace data flow** — where does the bad value originate? What called this with the bad value? Keep tracing up until you find the source. Fix at source, not at symptom.

## Phase 2: Pattern Analysis

1. **Find working examples** — locate similar working code in the same codebase.
2. **Compare against references** — if implementing a pattern, read the reference completely.
3. **Identify differences** — list every difference, however small. Don't assume "that can't matter."
4. **Understand dependencies** — what other components, settings, config, or environment does this need?

## Phase 3: Hypothesis and Testing

**Simple bugs (single plausible cause):** Sequential approach.
1. **Form single hypothesis** — "I think X is the root cause because Y." Be specific.
2. **Test minimally** — smallest possible change, one variable at a time.
3. **Verify** — did it work? Yes -> Phase 4. No -> form NEW hypothesis. Don't stack fixes.
4. **When you don't know** — say so. Don't pretend. Ask for help or research more.

**Complex bugs (multiple plausible causes):** Parallel hypothesis investigation.
When Phase 2 reveals 2-3 competing theories, dispatch a **debug team** — one agent per hypothesis, all investigating in parallel (read-only Explore agents). Each agent:
- States the hypothesis clearly
- Gathers evidence for/against
- Reports: confirmed, refuted, or inconclusive with evidence

The agent that confirms its hypothesis (or the strongest evidence) informs Phase 4. This is faster than sequential hypothesis testing for multi-component bugs.

## Phase 4: Implementation

1. **Create failing test case** — simplest possible reproduction, automated if possible.
2. **Implement single fix** — address the root cause, ONE change at a time. No "while I'm here" improvements.
3. **Verify fix** — test passes? No other tests broken? Issue resolved?
4. **If fix doesn't work** — count attempts. If < 3, return to Phase 1 with new information. If >= 3, STOP.

## After 3+ Failed Fixes: Question Architecture

Pattern indicating an architectural problem:
- Each fix reveals new shared state/coupling in different places
- Fixes require "massive refactoring" to implement
- Each fix creates new symptoms elsewhere

**STOP and escalate to user.** This is not a failed hypothesis — this is a wrong architecture.

## Red Flags — STOP and Follow Process

- "Quick fix for now, investigate later"
- "Just try changing X and see if it works"
- "Add multiple changes, run tests"
- "It's probably X, let me fix that"
- Proposing solutions before tracing data flow
- "One more fix attempt" when already tried 2+

All of these mean: STOP. Return to Phase 1.
