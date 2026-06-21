# Graduated Entries

Entries in this directory have been promoted from the live codex-learnings set into
production enforcement. A graduated entry's enforcement logic lives in a hook or
helper and runs on every applicable event — making the pre-flight check redundant.

Relocation is always `git mv` so `git log --follow <file>` preserves full history.
The H1 heading (`# C1`, `# P5`, etc.) is never changed — the born-tag invariant
is preserved. Live readers use non-recursive top-level `*.md` globs, so graduated
entries are excluded automatically.

## Graduation record

| Entry | Graduated to | Coverage scope | Mode | Date |
|-------|-------------|----------------|------|------|
| C1 | _lib/graduated_checks.check_c1_path_trust | language-agnostic (path-input thesis) | advisory | 2026-06-21 |
