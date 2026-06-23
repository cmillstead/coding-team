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
record above, and the non-recursive top-level `*.md` glob (the same sweep that
excludes graduated entries) still picks them up as live during pre-flight.

| Entry | Enforced slice | Residual (owned by Codex review) | Date |
|-------|---------------|----------------------------------|------|
| C17 | write-guard `check_path_safety` ("Case study #35"): Python-only (`.py`-gated), usage-site, substring-collision advisory — flags string ops on path-ish variables as a proxy; suppressed when a safe Path API (`Path(`/`.parts`/`.is_relative_to(`) co-occurs | Structural segment-alignment verification and non-Python path comparisons — owned by Codex cross-model review (deliberate division of labor: hooks catch syntactic signals; the reasoner owns structural theses) | 2026-06-21 |
| C5 | Rust AND Python: author-time ADVISORY via graduated_checks.py (PreToolUse Edit\|Write) — Rust gated by `.rs` extension, Python by test-file path; both nudge on a detected ungated external open, neither blocks. (Piloted as a Rust commit-block; downgraded to advisory after the post-apply gate found an open-ended false-block surface in the Rust line-parser.) | Blocking abandoned — an advisory false-positive is a harmless nudge, so FP precision is no longer load-bearing; the detector is a best-effort line-parser that may over- or under-fire on adversarial syntax. Structural/external-vs-hermetic discrimination remains owned by Codex review. **Findings:** (1) blocking viability needs detection that does not depend on hand-parsing the host language — Rust C5 had a positive signature + gold positives yet failed blocking because a line-parser cannot robustly parse Rust (comments/strings/braces/macros); revive only on a real AST (`syn`). (2) a blocking spike's FP corpus must include adversarial/synthetic syntax, not just real-corpus samples — the real-corpus FP=0 missed edges the gate later found. | 2026-06-22 |
