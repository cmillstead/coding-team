# Codex Learnings — Pre-flight Checklist

Anti-patterns that Codex cross-model review has repeatedly caught in Claude's plans and diffs.
The `/second-opinion` pre-flight checks every entry here BEFORE dispatching, so Codex spends its
rounds on novel problems instead of the same recurring mistakes. The post-review learning-capture
loop appends new recurring patterns here with the next ID.

**How to use (pre-flight):** check the plan/diff against every `P##` and `C##` below. Classify each
into `✓` (checked, clean), `FIXED` (violation found and fixed before dispatch), or `N/A(reason)`.
See `SKILL.md` → "Pre-flight — MANDATORY" for the coverage-line format.

**Seeded 2026-06-07** from accumulated memory (`feedback_codex_second_opinion`,
`feedback_path-trust-tiers`, `feedback_codex-cross-model-value`). This is v0 — small and honest.
It grows via learning capture, not by inventing slots.

---

## P — Plan patterns

Plans written from memory of the code are optimistic. These are the mismatches Codex catches when
it reads the actual code. Round 1 is mostly structural; round 2 mostly precision (see SKILL.md
round budgeting).

| ID | Pattern | Check before dispatch |
|----|---------|----------------------|
| P1 | **Phantom symbol** — plan references a field, type, function, or column that doesn't exist | Grep the codebase for every named symbol the plan touches. If it isn't there, the plan is describing code from memory, not reality. |
| P2 | **Wrong API name/shape** — wrong method name, signature, return type, or AST node name | Open the actual definition for every API the plan calls. Codesight/tree-sitter node names and SDK signatures are the usual offenders — confirm, don't recall. |
| P3 | **Stale command** — a shell/CLI command whose flags or subcommands no longer exist | Run `--help` (or check the CLI source) for every command the plan tells someone to run. Flags drift; verify the exact invocation. |
| P4 | **Wrong identifier** — nonexistent parameter, wrong variable name, or mis-scoped reference | Trace each variable/param named in the plan to its declaration. A name that "sounds right" but isn't there is a round-1 finding. |

## C — Code / diff patterns

Mistakes Codex catches in actual diffs that same-model audit rounds miss, because Claude's audit
reads the code with the assumptions that wrote it.

| ID | Pattern | Check before dispatch |
|----|---------|----------------------|
| C1 | **Single-gate path trust boundary** — validating a path-shaped field with one rule (e.g. `if value.contains("/")`) lets slashless inputs (`".."`, `"tmp"`, `"src"`) bypass the check and resolve against cwd. Caught as a CRITICAL slashless-bypass in the codesight MCP build. | Classify every path-shaped field into three tiers and validate accordingly: **(1) Identifier** (`repo` accepting `"engram"` OR an absolute path) — only path-form gets the prefix check. **(2) Filesystem path** (`path`, `repoPath`, `storagePath`) — ALWAYS `path.resolve` + require result under the trusted prefix, slash or not. **(3) Repo-relative** (`filePath`, `pathPrefix`) — reject any `..` segment via `path.posix.normalize` + segment split. Ask "identifier or filesystem path?" for each field; the rules differ. |

---

## Notes for learning capture

- Append a new row only when a finding is **recurring** (would apply to other plans/code), not a
  one-off project-specific logic error.
- If pre-flight missed something Codex then caught, the pattern description here is too weak —
  tighten the existing row rather than adding a near-duplicate.
- Keep "Check before dispatch" mechanical and verifiable — a step someone can actually run, not a
  principle to keep in mind.
