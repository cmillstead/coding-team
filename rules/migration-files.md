---
globs:
  - "**/migrations/**"
  - "**/alembic/**"
  - "**/migrate/**"
---

# Migration File Rules
<!-- Deploy source: scripts/deploy.sh copies this to ~/.claude/rules/ -->

- NEVER modify deployed migrations — always create a new migration for schema changes
- Include both up and down/rollback logic in every migration
- Test migrations against a real database, not mocks
- Add a comment at the top explaining what the migration does and why
- NEVER drop columns or tables without explicit user confirmation
