# Context Inheritance Matrix

This matrix closes the CS-5 retro action item (2026-03-25 decision: `memory/decisions/2026-03-25-context-inheritance-as-matrix.md`). Every code-touching agent must receive the style guide and design defaults — not just task-specific context. The matrix makes gaps visible: an empty cell where a code-touching agent does not receive a shared reference file is an obvious defect.

**Reading the cells:** Each cell states HOW the agent receives the file — the mechanism matters. "INSERT placeholder, orchestrator paste" means the orchestrator reads the file and fills a named section in the dispatched prompt. "Read in planning.md Context Inheritance" means the planning worker's own instructions tell it to Read the file directly. "—" means the agent does not receive this file and that is intentional (e.g., read-only reviewers need task context, not shared reference files).

| Reference file | planning-worker | design-team (Team Leader + workers) | ct-implementer | ct-builder | ct-reviewer | ct-qa |
|---|---|---|---|---|---|---|
| `~/.claude/golden-principles.md` | Read in `planning.md` Context Inheritance item 1 | Read in `design-team-context-retrieval.md`, passed as "## Golden Principles" section | INSERT placeholder via `execution.md` step 2 (architectural decisions tasks) | **Gap** — not wired; see note below | — (read-only reviewer) | — (read-only reviewer) |
| `~/.claude/code-style.md` | Read in `planning.md` Context Inheritance item 2 | Read in `design-team-context-retrieval.md`, passed as "## Code Style" section | INSERT placeholder via `execution.md` step 2 (code-language tasks) | INSERT placeholder via `execution.md` step 2 (code-language tasks) | — (read-only reviewer) | — (read-only reviewer) |
| `docs/team-memory.md` | Read in `planning.md` Context Inheritance item 3 (if exists) | Read in `design-team-context-retrieval.md`, passed as "## Team Memory" section | Relevant entries via `execution.md` step 2 Context section | **Gap** — not explicitly wired; see note below | — (read-only reviewer) | — (read-only reviewer) |
| `~/.claude/skills/coding-team/skills/second-opinion/codex-learnings-digest.md` | Read in `planning.md` Context Inheritance item 5 | **Gap** — not wired; see note below | INSERT placeholder via `execution.md` step 2 (all dispatch paths) | INSERT placeholder via `execution.md` step 2 (all dispatch paths; builder is sole agent on MICRO tasks) | — (read-only reviewer) | — (read-only reviewer) |

## Gaps Identified

The following cells are empty where wiring was arguably expected. These are noted for follow-up — they were not in scope for Slice C.

**ct-builder — golden-principles.md:** `execution.md` step 2 reads and passes `golden-principles.md` only into the "implementer prompt's Context section." The builder is dispatched on the same path on MICRO tasks (`commands/build.md:60-64`) but the instruction names only the implementer. On architectural tasks dispatched to the builder, golden-principles context is missing. Follow-up: add builder explicitly to the golden-principles paste instruction in `execution.md`.

**ct-builder — team-memory.md:** Same gap as above. The `execution.md` step 2 instruction reads team-memory and passes relevant entries to "the implementer prompt's Context section" — not to the builder prompt. Follow-up: extend the paste instruction to cover both implementer and builder.

**design-team — codex-learnings-digest.md:** The digest is generative — it helps authors avoid mistakes while writing plans/code. The design-team produces design docs (not implementation plans or code), so the need is lower. However, design workers write implementation recommendations that feed directly into the plan and may encode the same recurring mistakes. This gap is a judgment call deferred to a future iteration. Follow-up: evaluate whether design workers should receive the digest as an advisory section.

## Verification Evidence

Each cell was verified by reading the actual source files, not inferred:

- `planning.md` Context Inheritance: verified at lines 96–103 (items 1–5)
- `design-team-context-retrieval.md`: verified lines 49–63 (golden principles, code style, team memory sections)
- `execution.md` step 2: verified at lines 82–84 (code-style, golden-principles, team-memory paste instructions)
- `ct-implementer.md` Code Style INSERT: verified at lines 89–93
- `ct-builder.md` Code Style INSERT: verified at lines 89–93
- `ct-implementer.md` Codex Design Defaults INSERT: added in Slice C
- `ct-builder.md` Codex Design Defaults INSERT: added in Slice C
- `execution.md` codex digest paste: added in Slice C
- ct-reviewer and ct-qa: verified as read-only agents with no INSERT placeholders for shared reference files
