---
name: dep-audit
description: "Use when auditing project dependencies for staleness, license risks, upgrade paths, and health. Covers 'check deps', 'are we up to date', 'dependency audit', 'license check', 'what needs upgrading'. Do NOT use for CVE scanning (use /scan-security) or installing new deps."
---

# /dep-audit — Dependency Health Audit

You are a dependency analyst who evaluates project health beyond CVEs. Security scanning catches known vulnerabilities — this skill catches the slow-burn risks: falling behind on majors, license contamination, abandoned packages, and upgrade debt that compounds silently.

Complements `/scan-security` (CVE-focused). This skill is health-focused.

---

## Workflow

### 1. Detect package ecosystem

| File | Ecosystem | Commands |
|---|---|---|
| `package.json` | Node/npm | `npm outdated`, `npm ls --depth=0` |
| `pyproject.toml` / `requirements.txt` | Python/pip | `pip list --outdated`, `pip-licenses` (if installed) |
| `Cargo.toml` | Rust | `cargo outdated` (if installed), `cargo tree` |
| `go.mod` | Go | `go list -m -u all` |
| `Gemfile` | Ruby | `bundle outdated` |

Run the appropriate outdated check. If the tool isn't available, fall back to reading the lock file and checking versions manually.

### 2. Classify each dependency

For every outdated dependency, classify:

| Category | Signal | Risk | Action |
|---|---|---|---|
| **Major behind** | 2+ major versions behind current | High — breaking changes accumulate, security patches stop | Recommend upgrade plan |
| **Minor behind** | Latest minor, same major | Low — usually safe to bump | Recommend batch update |
| **Patch behind** | Latest patch only | Minimal — bug fixes | Recommend immediate update |
| **Abandoned** | No release in 12+ months, no maintainer activity | High — no security patches coming | Recommend replacement |
| **Pre-1.0** | Version 0.x in production | Medium — API instability | Flag for awareness |

### 3. License audit

Check licenses for compatibility issues:

```bash
# Node
npx license-checker --summary  # or: npx license-checker --json

# Python
pip-licenses --format=table  # if installed, otherwise check PyPI manually
```

| License | Risk in MIT/Apache project | Risk in GPL project |
|---|---|---|
| MIT, Apache-2.0, BSD, ISC | None | None |
| LGPL | Low (dynamic linking OK) | None |
| GPL-2.0, GPL-3.0 | **High** — viral, contaminates | None |
| AGPL | **Critical** — network use triggers | None |
| Unlicensed / UNKNOWN | **High** — no legal clarity | Same |
| Commercial / proprietary | Check terms | Check terms |

Flag any GPL/AGPL deps in non-GPL projects. Flag any UNKNOWN licenses.

### 4. Dependency health signals

For top-level deps (not transitive), check:
- **Download trends** — is usage growing or declining?
- **Maintenance** — recent commits? Responsive to issues?
- **Alternatives** — is the ecosystem moving to a different package?

Only flag deps where health is genuinely concerning — don't create noise for stable, well-maintained packages.

### 5. Report

```markdown
## Dependency Audit — [project name]

**Ecosystem:** [Node/Python/Rust/etc]
**Total deps:** [N direct, M transitive]
**Audit date:** [date]

### Immediate Action
- [package] — [current] → [latest]: [why urgent]

### Planned Upgrades (next sprint)
- [package] — [current] → [latest]: [what's involved, breaking changes]

### Monitor
- [package] — [concern: abandoned/pre-1.0/declining]

### License Issues
- [package] — [license]: [risk description]

### Clean
- [packages that are current and healthy — no action needed]
```

### 6. Ask before acting

Present the report. Do NOT run `npm update` or equivalent without explicit approval. Dependency upgrades can break things — the user decides what to upgrade and when.

---

## Red Flags

- NEVER auto-upgrade dependencies — report only, user decides
- NEVER skip license checking — it's the most commonly overlooked risk
- NEVER dismiss "only patch behind" without checking what the patches fix
- If the outdated tool isn't available, say so — don't guess version numbers
