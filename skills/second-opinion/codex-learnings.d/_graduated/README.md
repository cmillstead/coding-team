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
| C5 | Rust: commit-time staged-set BLOCK via git-safety-guard.py (`check_c5_test_hermeticity`, staged-index scan; blocks DETECTED ungated external opens). Python: author-time ADVISORY via graduated_checks.py (Edit\|Write, test-file-path-gated). Rust FP=0/984 fns + 0 trap FP, recall 4/4 gold positives, FN 2 fail-open-safe; Python A_precise FP=0 (fires on nothing — no positive corpus), advisory-only. | Python thesis + structural/external-vs-hermetic discrimination + Rust off-idiom FN (helper-wrap, inline-comment-spoofed gate) + `git push`/`git -c k=v commit` applicability misses — all fail-open-safe, owned by Codex review. **Blocking is viable only where the violation has a POSITIVE, precisely-detectable signature AND a real positive corpus.** Rust C5 qualified: ungated `#[ignore]` on real external opens is positively detectable and has gold positives. Python C5 did not: the suite is hermetic-by-construction, so there is no violation surface — "absence of a gate" is negative-reasoning-bound and unprovable for blocking. Future blocking-graduation candidates should be selected by this test, not retrofitted onto negative-reasoning entries. | 2026-06-22 |
