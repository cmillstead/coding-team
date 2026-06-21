# P1

| ID | Pattern | Check before dispatch |
|----|---------|----------------------|
| P1 | `@tags: plan-symbol; reasoning-shape; scope:plan; floor` **Phantom symbol** — plan references a field, type, function, or column that doesn't exist | Grep the codebase for every named symbol the plan touches. If it isn't there, the plan is describing code from memory, not reality. |

**Design default:** Verify every symbol the plan names exists in the codebase before writing the plan — grep for each field, type, function, and column rather than recalling from memory.
