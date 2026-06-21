# P2

| ID | Pattern | Check before dispatch |
|----|---------|----------------------|
| P2 | `@tags: plan-symbol; reasoning-shape; scope:plan; floor` **Wrong API name/shape** — wrong method name, signature, return type, or AST node name | Open the actual definition for every API the plan calls. Codesight/tree-sitter node names and SDK signatures are the usual offenders — confirm, don't recall. |

**Design default:** Open the actual definition for every API, SDK method, and tree-sitter node the plan calls — never write a method name, signature, or return type from memory.
