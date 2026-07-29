# C27

`@tags: migration-parity; reasoning-shape; scope:both`

**Pattern:** A self-healing/repair migration (or any code that recreates a schema object on a
DEPLOYED DB) validates only the EXISTENCE of the objects it depends on, not their SHAPE or
NAMESPACE — and SQLite's laziness turns each gap into a wedge that only fires later: (1)
`CREATE TRIGGER` referencing a column is accepted even when the column does not exist (columns
resolve at FIRE time, not creation), so repairing against a non-canonical table "succeeds" and
then breaks EVERY statement that fires the trigger (`no such column`); (2) unqualified
schema-object references resolve TEMP-before-MAIN — a bare `PRAGMA table_info(t)` reads a
same-named `temp.t` instead of `main.t`, and an unqualified `DROP TRIGGER` drops the TEMP
twin first (making the following `CREATE` fail "already exists" and the repair roll back on
every startup); (3) identifier comparisons done case-sensitively reject validly-cased schemas
(`NODE_ID` ≡ `node_id` to SQLite). Caught on engram migration 45 (vault-bound-trigger repair)
across 2 Codex challenge rounds: the initial code repaired on table-existence alone (every
node delete would fail on a partial `sync_state`); the first guard used an unqualified
`table_info` (TEMP shadow bypassed it) and a case-sensitive column Set. All four
same-model auditors and the Mode 1 review missed all of it; the adversarial challenge
reproduced each with the real driver.

**Check before dispatch:** for any migration/startup code that DROPs+CREATEs or repairs a
schema object on a deployed DB: (a) does it validate the SHAPE (required columns via
`pragma('main.table_info(...)')`, case-folded names) of every table the recreated object
references — not just table existence — and fail SAFE (skip + warn, leave the old object
working) when the shape is non-canonical? (b) is every object reference schema-qualified
(`main.`) so a same-named TEMP table/trigger cannot shadow the read, the DROP, or the guard?
(c) remember `sqlite_master` queries are main-only but bare `PRAGMA`/`DROP` are NOT — a
mixed pair silently checks one namespace and mutates another. Add tests for: partial/
non-canonical table shape (repair skipped, DB unchanged), same-named TEMP table AND TEMP
trigger present (repair still lands on main), and uppercase-declared canonical columns
(repair still proceeds).

**Design default:** Repair/self-heal code on a deployed DB validates shape (case-folded,
`main.`-qualified `table_info`) before recreating any object that references it, qualifies
every DROP/lookup with `main.`, and fails safe (skip + warn) on any non-canonical state —
existence checks alone are wedge-installers.
