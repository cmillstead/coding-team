# C23

`@tags: command-grammar; reasoning-shape; scope:both`

**Pattern:** A generic "success" early-return (an `EMPTY`/`OK`/`return None`/`return []` for the no-data case) is placed EARLIER in the control flow than a REQUIRED validation gate, so a subset of invalid inputs hits the early-return and silently succeeds instead of raising the mandated teaching-error. The gate looks present in the source, but a specific input class (usually the zero/empty case) never reaches it.

Concretely caught: a `/kb` planner where `synthesize` must error when `<2` KBs have hits. The `<2` guard sat AFTER the generic `if no hits -> EMPTY (exit 0)` return, so `synthesize` with **zero** hits returned EMPTY (success) instead of the "needs >=2 KBs" error — the guard only ever fired for the exactly-1 case. Same shape: a required "must have N of X" or "not allowed in mode M" check ordered after an empty/degenerate-case shortcut.

**Check before dispatch:** For every REQUIRED validation/teaching-error the spec names (a "must", a "reject when", a "needs >= N"), trace the control flow and confirm NO earlier early-return (empty-result, no-op, default-success, cache-hit, "nothing to do") can intercept the SAME inputs the gate is supposed to reject — especially the zero/empty boundary. If an early success-return precedes a required gate, move the gate before the return (or make the return conditional on the gate having passed). Add an explicit test at the degenerate boundary (0 items, empty set), not just the near-boundary (1 item).

**Design default:** Order required rejection gates BEFORE any generic success/empty early-return, and test each gate at the zero/empty boundary — never assume the "no data" shortcut is safe for an input the spec says must be rejected.
