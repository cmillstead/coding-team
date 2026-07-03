# C23

`@tags: tenant-isolation; migration-parity; reasoning-shape; scope:diff`

**Pattern:** A migration that adds/normalizes a least-privilege DB role normalizes ATTRIBUTES
(`ALTER ROLE … NOSUPERUSER NOBYPASSRLS …`) but does NOT revoke stale table/schema GRANTs or role
MEMBERSHIPS — so a dirty pre-existing role (reused cluster) keeps grants that silently widen a column
fence (inherited `app_user` membership re-opens tenant DML; a table-level `GRANT SELECT` exposes the
fenced column). Sibling trap: the boot guard asserts the role is restricted *by literal name* from
another pool, so a pool whose URL points at the WRONG role (superuser) is never caught, and the guard
may be wired AFTER the consumer that already began using the pool.

**Check before dispatch:**
1. If the diff adds a `CREATE ROLE` / `ALTER ROLE` for a narrow role, confirm the migration also
   `REVOKE ALL PRIVILEGES ON <fenced table>` + `… ON ALL TABLES IN SCHEMA public` + `… ON SCHEMA
   public` FROM the role BEFORE re-granting only the intended columns (table-level REVOKE clears
   column privileges too). Idempotent least-privilege even on a dirty role.
2. If a boot guard validates the role, confirm it connects THROUGH the actual pool and asserts
   `current_user = session_user = <role>`, `pg_auth_members` count = 0 **in BOTH directions**, and live
   `has_column_privilege`(fenced)=false + (allowed)=true — not just a `pg_roles` name/attribute check.
   **BOTH directions matters:** (a) roles the fenced role is a MEMBER OF (`m.member = <role>` — inherits
   app_user's tenant DML); AND (b) roles that are MEMBERS OF the fenced role (`m.roleid = <role>`) — the
   more dangerous, easily-missed direction: `GRANT <fenced_role> TO app_user` makes the fenced role's
   permissive `… USING (true)` RLS policy APPLY to app_user (Postgres applies a `TO role` policy to inherited
   members; permissive policies OR → all rows) → full cross-tenant read. A guard checking only `m.member`
   passes this attack (Codex caught it on Mabel M3 email webhook `email_webhook_resolver`, 2026-07-02).
3. Confirm that guard runs BEFORE any consumer that uses the pool is constructed (queue Workers
   consume on construction).

**Design default:** When you add a narrow least-privilege role, REVOKE-before-GRANT in the migration
and validate the live connection's identity + column privileges at boot, before starting consumers —
never trust a name-only attribute check on a role that could carry inherited grants.
