---
name: doc-sync
description: Update project documentation to match what just shipped
---

# /doc-sync — Post-Ship Documentation Update

Sync project documentation with the code that just shipped. Catches doc drift that per-task checks and the execution-phase drift scan may have missed.

## Workflow

1. **Gather context:**
   ```bash
   # What changed
   git diff main...HEAD --stat
   git diff main...HEAD --name-only

   # All doc files
   REPO_ROOT=$(git rev-parse --show-toplevel)
   find "$REPO_ROOT" -maxdepth 3 -name "*.md" -not -path "*/.git/*" -not -path "*/node_modules/*"
   ```

2. **Audit each doc file against the diff:**

   | Doc file | Check |
   |---|---|
   | README.md | Features, install instructions, usage examples, file structure |
   | ARCHITECTURE.md | Component descriptions, diagrams, design decisions |
   | CONTRIBUTING.md | Setup instructions, test commands, workflow descriptions |
   | CLAUDE.md | Project structure, commands, build/test instructions |
   | CHANGELOG.md | Latest entry covers all shipped changes |
   | Any other .md | Cross-reference against diff for stale content |

3. **For each file:**
   - **Factual corrections** (stale paths, counts, commands): fix directly.
   - **Narrative changes** (positioning, philosophy, large rewrites): ask the user.
   - **Missing documentation** (new features not documented): add entries.

4. **Cross-doc consistency:**
   - README feature list matches CLAUDE.md descriptions?
   - ARCHITECTURE component list matches file structure?
   - Version numbers consistent across files?
   - Every doc file reachable from README or CLAUDE.md?

5. **Commit documentation updates:**
   ```bash
   git add <updated-doc-files>
   git commit -m "docs: update project documentation for <feature>"
   ```

## What This Catches (That Per-Task Checks Miss)

- Cross-cutting drift: feature A's docs mention feature B, which also changed
- File structure listings that need multiple entries updated
- CHANGELOG entries that need voice polish
- Cross-doc contradictions (README says one thing, ARCHITECTURE says another)
- Discoverability gaps (new doc file not linked from README)

## Red Flags

- NEVER overwrite or regenerate CHANGELOG entries — polish wording only
- NEVER remove documentation sections without asking
- NEVER update version numbers without asking
- Always read a file completely before editing it
