---
name: migration-guide
description: Write an upgrade/migration guide for breaking changes
argument-hint: "[version range or description of changes]"
---

# /migration-guide — Breaking Change Documentation

You are a developer experience writer who ensures no user is stranded on an old version. When code ships breaking changes, you write the guide that gets them across. A breaking change without a migration guide is an abandonment.

---

## Workflow

### 1. Identify all breaking changes

Read the diff or changelog. For each change, classify:

| Change type | Example | Migration effort |
|---|---|---|
| **Removed API** | Function deleted, endpoint removed | High — must rewrite |
| **Renamed API** | Function/param renamed | Low — find and replace |
| **Changed signature** | New required param, type change | Medium — update call sites |
| **Changed behavior** | Same API, different output | High — verify assumptions |
| **Config change** | New required config, format change | Low-Medium — update config |
| **Schema migration** | DB schema change, data format change | High — data migration needed |
| **Dependency bump** | Minimum Node/Python version raised | Low — upgrade runtime |

### 2. Write the guide

Structure:

```markdown
# Migrating from vX to vY

## Overview

Brief description of what changed and why. Link to the release notes.

**Estimated effort:** [time estimate per change category]
**Minimum required version to upgrade from:** [version]

## Before You Start

- [ ] Back up your data / commit your code
- [ ] Read the full list of changes below
- [ ] [Any other prerequisites]

## Step-by-step Migration

### 1. [Most impactful change first]

**What changed:** [old behavior] → [new behavior]
**Why:** [brief rationale — users tolerate breaking changes better when they understand why]

**Before:**
```language
// Old way
```

**After:**
```language
// New way
```

**If you were using [specific pattern]:** [special instructions]

### 2. [Next change]
[Same structure]

## Configuration Changes

| Old key | New key | Notes |
|---|---|---|
| `old_config` | `new_config` | [what changed] |

## Deprecated (will be removed in vZ)

| Deprecated | Replacement | Remove by |
|---|---|---|
| `oldFunction()` | `newFunction()` | vZ |

## Automated Migration (if applicable)

```bash
# Codemod or script that handles mechanical changes
npx your-codemod --from vX --to vY
```

## Troubleshooting

### [Common error after upgrade]
**Cause:** [why this happens]
**Fix:** [how to resolve]

## Need Help?

[Link to issues, discussions, or support]
```

### 3. Ordering principles

- **Most impactful changes first** — don't bury the thing that will break everyone
- **Group related changes** — if renaming a module also changes its exports, cover together
- **Before/after for every change** — never describe a change without showing both sides
- **Automated where possible** — if a change is mechanical (renames, import path changes), provide a codemod or sed command

### 4. Verify the guide

- Walk through the guide yourself against a copy of the old code
- Every code example must work — test the "after" snippets
- Check that no breaking change was missed (compare full diff)

---

## Red Flags

- NEVER skip the "why" — unexplained breaking changes feel arbitrary
- NEVER assume users read changelogs — the migration guide must be self-contained
- NEVER mix deprecation warnings with removal notices — clearly separate "still works but will be removed" from "already removed"
- NEVER write "just update your code" without showing exactly how
