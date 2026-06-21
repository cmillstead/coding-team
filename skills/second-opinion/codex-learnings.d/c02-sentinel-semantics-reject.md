# C2

| ID | Pattern | Check before dispatch |
|----|---------|----------------------|
| C2 | `@tags: sentinel-semantics; provable; scope:diff` **New `validate()`/guard rejects a value that is a valid sentinel elsewhere** — adding a "reject 0/empty/-1" rule without checking how the field is consumed. E.g. rejecting `rebuild_interval == 0` when `sync.rs` guards `if rebuild_interval > 0 { rebuild }`, so `0` means "disabled" — the validation turns a supported config into a startup error. Caught on the axon code-scan remediation diff (CODE-MED-5). | Before adding a "reject N" rule, grep every consumer of the field (`> 0`, `== 0`, `is_empty()`, `.unwrap_or`, match arms). If ANY consumer treats the rejected value as a sentinel/disable/default mode, do not reject it. A scan finding that says "reject 0" may be wrong about the value being invalid — verify against usage. |

**Design default:** When a spec says "reject 0/empty/-1," first map the field's consumers (`> 0`, `== 0`, `is_empty()`, match arms); if any treats that value as disable/sentinel/default, keep it valid and validate a different bound.
