# P1

| ID | Pattern | Check before dispatch |
|----|---------|----------------------|
| P1 | `@tags: plan-symbol; reasoning-shape; scope:plan; floor` **Phantom symbol** — plan references a field, type, function, or column that doesn't exist | Grep the codebase for every named symbol the plan touches. If it isn't there, the plan is describing code from memory, not reality. |
