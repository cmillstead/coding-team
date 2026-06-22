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

## Partial enforcement (entry stays live)

Entries listed here have a hook that covers a SLICE of their thesis, but the entry
remains LIVE in the top-level `codex-learnings.d/` because the hook is not full
coverage. These are NOT graduated entries — they do not appear in the Graduation
record above, and `_CARRIER_GLOB` still picks them up as live during pre-flight.

| Entry | Enforced slice | Residual (owned by Codex review) | Date |
|-------|---------------|----------------------------------|------|
| C17 | write-guard `check_path_safety` ("Case study #35"): Python-only (`.py`-gated), usage-site, substring-collision advisory — flags string ops on path-ish variables as a proxy; suppressed when a safe Path API (`Path(`/`.parts`/`.is_relative_to(`) co-occurs | Structural segment-alignment verification and non-Python path comparisons — owned by Codex cross-model review (deliberate division of labor: hooks catch syntactic signals; the reasoner owns structural theses) | 2026-06-21 |
