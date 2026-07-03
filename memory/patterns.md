---
name: Cross-project recurring patterns
description: Patterns discovered across multiple projects that inform future design and review — auto-maintained by completion phase
type: feedback
---

# Recurring Patterns

- Anti-circularity via externally-seeded fixtures: when a function is duplicated across languages/modules by invariant (e.g. the same hash implemented in Rust and JS), give both implementations a single shared fixture of externally-computed canonical values. Neither copy can drift without failing CI — the fixture is the source of truth, not either implementation. (first seen 2026-06-12, baxter FNV-1a parity guard)
- Cross-model adversarial challenge catches what same-model audit misses: in-house review/harden/QA returned PASS/SOUND, but a different model's *challenge* mode (not review mode) surfaced a P1 sandbox escape. Review confirms intent; challenge attacks it — run both, they are not substitutes. (first seen 2026-06-12, baxter dangling-symlink P1)
- Security fixes under TDD prove the exploit RED first: write the test that demonstrates the escape/out-of-bounds/injection succeeding, watch it fail to be blocked, then close it. Prevents shipping a "fix" that doesn't actually fix. (first seen 2026-06-12, baxter resolve_path V1 + dangling-symlink)
