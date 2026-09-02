---
name: doc-sync
description: "Use after shipping a feature to update project documentation. Reads all docs, cross-references the diff, updates README/ARCHITECTURE/CONTRIBUTING/CLAUDE.md to match what shipped. Polishes CHANGELOG, cleans up TODOs."
---

# /doc-sync — Post-Ship Documentation Update

Sync project documentation with the code that just shipped. Catches doc drift that per-task checks and the execution-phase drift scan may have missed.

## When to Use

- After Phase 6 completion — final documentation polish
- After a PR merges — ensure docs match merged code
- When user says "update the docs", "sync documentation"

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

3. **CLAUDE.md reference staleness scan (flag-only — never auto-edit):**

   Regex-extract the backtick-quoted refs named in CLAUDE.md, then check each path-like ref (one containing `/`) against the CURRENT working tree. A path-like ref that does NOT resolve in the working tree is a *candidate* stale ref.

   ```bash
   REPO_ROOT=$(git rev-parse --show-toplevel)
   # Extract backtick-quoted refs (paths, function names, script names) from CLAUDE.md
   grep -oE '`[^`]+`' "$REPO_ROOT/CLAUDE.md" | tr -d '`' | sort -u > /tmp/claude-refs.txt
   # For each ref that looks like a path, check whether it still resolves
   while read -r ref; do
     case "$ref" in
       */*) [ -e "$REPO_ROOT/$ref" ] || echo "CANDIDATE STALE: $ref" ;;
     esac
   done < /tmp/claude-refs.txt
   ```

   This maps onto doc-sync's existing detect-deterministic / repair-with-LLM shape: the scan is the deterministic detector; a human is the repairer. **CRITICAL — this step FLAGS candidates for human review only. NEVER hard-fail the workflow and NEVER auto-edit CLAUDE.md from this scan.** A measured 36% false-positive rate (refs that moved, are intentionally aspirational, or live outside the working tree) makes any automatic action unsafe. Present the candidate list to the user under the same "narrative changes → ask the user" rule as step 4.

4. **For each file:**
   - **Factual corrections** (stale paths, counts, commands): fix directly.
   - **Narrative changes** (positioning, philosophy, large rewrites): ask the user.
   - **Missing documentation** (new features not documented): add entries.

5. **Cross-doc consistency:**
   - README feature list matches CLAUDE.md descriptions?
   - ARCHITECTURE component list matches file structure?
   - Version numbers consistent across files?
   - Every doc file reachable from README or CLAUDE.md?

6. **Commit documentation updates:**
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
