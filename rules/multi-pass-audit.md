# Multi-Pass Audit Pattern

Single-pass audits miss cross-file, behavioral, and migration residue issues. When auditing or scanning code, run 2+ passes with a different focus per pass:

1. **Pass 1 — Agent-internal:** Check each file/agent in isolation for correctness
2. **Pass 2 — Cross-file consistency:** Check interfaces, imports, and shared state across files
3. **Pass 3 — Behavioral executability:** Verify instructions are actionable, not just syntactically correct
4. **Pass 4 — Migration residue:** Check for stale references, dead code, or incomplete refactors

Stop when a pass comes back clean. A minimum of 2 passes is required.

This applies to:
- `/scan-code`, `/scan-security`, `/scan-product`, `/scan-adversarial`
- `/harness-engineer audit`
- Any code review or audit workflow

Known rationalization: "The first pass was thorough enough" — single-pass audits consistently miss 20-40% of findings that cross-file or behavioral passes catch.
