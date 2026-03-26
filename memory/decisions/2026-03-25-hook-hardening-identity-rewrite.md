# Decision: Apply Identity Framing to All Hooks

**Date:** 2026-03-25
**Context:** PR #19 (13 hooks hardened) and PR #20 (selective-fix rationalization closed). Hooks were using imperative warnings ("Do not do X") which agents treated as advisory suggestions.
**Decision:** Rewrite all hook warning messages to use identity framing ("You are a zero-warning engineer") and named rationalizations ("The rationalization 'only warnings, no errors' is a compliance failure"). Every hook that issues a warning now frames it as a professional standard, not an external prohibition.
**Rationale:** Same principle as the CLAUDE.md identity rewrite (Case 30). An agent told "you are a zero-warning engineer" treats warnings as below its standard. An agent told "do not skip warnings" treats the instruction as overridable. Hook warnings that use identity framing produce less pushback and fewer bypass attempts.
**Consequences:** 13 hooks rewritten with identity framing. Named rationalizations added to 8 hooks. Performance optimizations (fast-path returns, input validation) added to prevent hooks from slowing down normal operations.
