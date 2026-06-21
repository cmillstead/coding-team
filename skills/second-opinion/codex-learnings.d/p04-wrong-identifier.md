# P4

| ID | Pattern | Check before dispatch |
|----|---------|----------------------|
| P4 | `@tags: plan-symbol; reasoning-shape; scope:plan; floor` **Wrong identifier** — nonexistent parameter, wrong variable name, or mis-scoped reference | Trace each variable/param named in the plan to its declaration. A name that "sounds right" but isn't there is a round-1 finding. |

**Design default:** Trace every variable and parameter the plan names to its declaration site in the actual source — never include an identifier that only "sounds right."
