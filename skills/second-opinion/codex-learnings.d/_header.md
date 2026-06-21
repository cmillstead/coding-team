# Codex Learnings — Pre-flight Checklist

Anti-patterns that Codex cross-model review has repeatedly caught in Claude's plans and diffs.
The `/second-opinion` pre-flight checks every entry here BEFORE dispatching, so Codex spends its
rounds on novel problems instead of the same recurring mistakes. The post-review learning-capture
loop appends new recurring patterns here with the next ID.

**How to use (pre-flight):** the `/second-opinion` engine in `SKILL.md` derives the change's
signals ONCE, then classifies every live entry into exactly TWO buckets — `applicable`
(deep-checked) or `dismissed`. An entry is `dismissed` for EXACTLY ONE of two reasons:
`scope-mismatch` (its `scope:` excludes the current mode — a `scope:diff` entry in a plan review
or a `scope:plan` entry in a diff review; `scope:both` is never scope-dismissed) OR `no-signal`
(an in-scope `provable` category whose signal a grep CONFIRMS absent). EVERYTHING else is
`applicable` and deep-checked: a signal match, a `reasoning-shape` entry, a `floor` entry (P1–P4),
an untagged (newly-appended) entry, or an UNKNOWN/ambiguous derivation. This scopes the expensive deep-check EFFORT to the
applicable subset (typically 4–8 entries, not the full live set) while still ACCOUNTING for
every entry by ID. The tag vocabulary, grep battery, and audit-line format below are read at
SKILL.md Step 1. Bulk-by-category dismissal is BANNED — see the rationalization block.

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


## C — Code / diff patterns

Mistakes Codex catches in actual diffs that same-model audit rounds miss, because Claude's audit
reads the code with the assumptions that wrote it.

| ID | Pattern | Check before dispatch |
|----|---------|----------------------|



## Tag schema & vocabulary

Each entry's Pattern cell is prefixed with an inline-code `@tags:` token (additive; no content
change; no renumber; table-safe because an inline-code span contains no `|`). Greppable via
``grep -o '@tags:[^`]*'``. Token grammar:

`@tags: <category>[; <category>…]; <provable|reasoning-shape>; scope:<plan|diff|both>[; floor]`

- **category** — one or more values from the closed enum below. An off-enum category means the
  engine read an unrecognized token — treat the entry as untagged (floor-default).
- **provable** — a grep can RELIABLY confirm this category ABSENT, so a confirmed-absent grep may
  dismiss the entry.
- **reasoning-shape** — a grep CANNOT confirm absence; the entry is NEVER dismissed, it always
  deep-checks. (`reasoning-shape` describes what proves NON-applicability, not what the check does —
  the entry's own "Check before dispatch" may still involve greps/reads.)
- **scope** — `plan` (prose reviews), `diff` (code reviews), or `both`.
- **floor** — reserved for always-applicable entries (P1–P4 plan-symbol concerns; any
  untagged/unclassifiable entry defaults here). A `floor` entry is always `applicable` WHEN IN SCOPE — scope-mismatch is checked first, so a `scope:plan` floor entry (P1–P4) is correctly scope-dismissed in a pure `diff` review.

**Category enum (17):**
`plan-symbol · negative-existence · ambiguity-guard · helper-reuse · metric-aggregate · path-input ·
path-equality · sentinel-semantics · ci-config · lossy-stash · test-hermeticity · command-grammar ·
select-threading · concurrency-lock · default-flip · migration-parity · tenant-isolation`

## Grep battery (provable categories only)

A signal FIRES for a category if ANY pattern below matches the diff hunks (DIFF mode) or the plan
prose (PLAN mode). Patterns are deliberately BROAD — over-matching only costs a cheap `✓`;
under-matching risks a silent skip, which is the dangerous direction. `reasoning-shape` categories
have NO battery (they always floor). Each pattern set is DISTILLED from the named category's entries'
existing "Check before dispatch" prose — do NOT invent new criteria.

| Category (provable) | Entries | Fire if ANY matches |
|---------------------|---------|---------------------|
| `path-input` | C1 | field name `(path\|dir\|file\|repo\|root\|prefix\|dest\|src)` OR a call `path.resolve\|open(\|fs::\|include_str!\|Path(\|join(` on a string OR a single-gate `.contains("/")` |
| `path-equality` | C17 | `ends_with\|starts_with\|strip_suffix\|strip_prefix\|contains(` used to compare TWO paths for sameness, OR a `same_file`/`is_same`/path-identity helper |
| `sentinel-semantics` | C2 | a new `validate`/guard rejecting `0`/`empty`/`-1`/`< 1`, OR `is_empty()\|== 0\|reject\|return Err` near a config/interval/threshold field |
| `ci-config` | C3 | touched `.github/workflows/*.yml\|Makefile\|noxfile\|tox.ini` OR `maturin\|pip install -e\|setup-python\|venv\|activate` |
| `test-hermeticity` | C5 | a test (`#[test]\|def test_\|it(\|fn test`) that opens a real DB/index/socket/daemon (`open(\|connect\|::open\|RocksDB\|sqlite\|TcpStream\|reqwest\|index`) without a temp/in-memory fixture |
| `command-grammar` | C10, C14 | a guard/classifier that models CLI flags (`has_flag\|starts_with("-")\|--\|arg ==\|match flag\|allowlist\|deny`) OR an exec-wrapper/interpreter unwrap (`exec\|sudo\|env \|node -e\|sh -c\|-c \|--eval`) |
| `select-threading` | C11 | a new alternative score/weight/override threaded via `unwrap_or\|max_by\|sort_by\|partial_cmp\|rerank\|boost` into existing selection |
| `metric-aggregate` | P31, C11 | an `Option`-returning per-unit metric whose aggregate skips `None` (`filter_map\|flatten\|\.iter().filter(.*is_some\|skip None\|average\|mean`) |
| `concurrency-lock` | C12 | `lock\|mutex\|acquire\|release\|TTL\|setInterval\|lease\|owner_pid\|kill\(pid\|INSERT OR IGNORE\|DELETE WHERE id` OR a `CREATE TABLE` whose name matches `(lock\|lease\|sync\|consolidation)` |

`metric-aggregate` also appears on P31; P31 is `provable` (battery above) but its sibling reasoning
about zero-vs-N/A is part of its deep-check, not its dismissal. `command-grammar` on P3 is `floor`
(a command named in plan PROSE — no diff to grep), whereas on C10/C14 it is `provable` (a real diff
exhibits the grammar).

## Audit-line format

The engine emits exactly this block before dispatch. Every live entry appears EXACTLY ONCE, in
`applicable` OR `dismissed` (G-account). `floor-note` is an ADDENDUM annotating which `applicable`
IDs got there by floor rather than a signal match — floor IDs are NOT listed twice and are NOT a
third bucket.

```
Pre-flight scope:
  mode: <plan|diff>
  signals: <category(evidence), …>
  applicable(N): <IDs> → ✓ <ids> | FIXED <ids>     (includes floor + reasoning-shape + matched)
  dismissed(M): <ID N/A(scope-mismatch:<entry-scope> vs mode:<plan|diff>)> | <ID N/A(no-signal:cat, evidence:<grep>)> …
  total: N + M = <live count>   floor-note: of the applicable, <ids> were floored (not signal-matched)
```

Each dismissed entry carries EXACTLY ONE of two reasons: `scope-mismatch:<entry-scope> vs mode:<plan|diff>`
(its `scope:` excludes the current mode) or `no-signal:<cat>, evidence:<grep that confirmed absence>`
(in-scope `provable` category proven absent). No other dismissal reason is valid — there is no third
bucket and no third reason. `<live count>` is COMPUTED from the file at run time — never a hardcoded
number. If `N + M` does not equal the live entry count, an entry was dropped: recount and re-emit.
`<live count>` = number of `.md` files in `codex-learnings.d/` EXCLUDING `_header.md`.

## Banned rationalizations (pre-flight engine)

These are bypasses, not exemptions:
- "Bulk-dismiss this whole category, it obviously doesn't apply" — BANNED. Every entry is accounted
  for BY ID; you may dismiss an individual `provable` entry only with a confirmed-absent grep cited
  as evidence. Bulk-by-category dismissal reintroduces the skip loophole.
- "This change is simple/trivial/small, skip the floor" — NO. Size NEVER exempts a floor entry.
  P1–P4 always deep-check on plan reviews regardless of perceived simplicity.
- "I read this `reasoning-shape` entry and it's fine, so dismiss it" — NO. Reading-to-rule-out IS
  the deep-check; its home is `applicable`→`✓`, never `dismissed`. `reasoning-shape` entries are
  never dismissed.
- "This entry has no `@tags` yet, so skip it" — NO. Untagged ⇒ floor (keystone) ⇒ always
  deep-checked.
- "Empty applicable-set, so the change is clean, pass it" — NO. An empty applicable-set on a change
  with ≥1 non-comment code line is a FINDING → escalate to a full check (G-empty/G-escalate).

## Notes for learning capture

- Add a new entry only when a finding is **recurring** (would apply to other plans/code), not a
  one-off project-specific logic error.
- If pre-flight missed something Codex then caught, the pattern description here is too weak —
  tighten the existing entry file rather than adding a near-duplicate.
- Keep "Check before dispatch" mechanical and verifiable — a step someone can actually run, not a
  principle to keep in mind.
- **Every new entry is a NEW FILE** in this directory (D196 drop-folder layout): filename
  `<YYYYMMDD-HHMMSS>-<rand4>-<slug>.md` (UTC datetime + 4 random hex chars for concurrency safety).
  Generate the random suffix: `python3 -c "import secrets; print(secrets.token_hex(2))"`. NEVER
  reuse a prior filename or hand-pick a sequential number — the filename stem is the entry's canonical ID.
- Every new entry is BORN TAGGED: the `@tags:` token (category + `provable`/`reasoning-shape` +
  `scope:`) is written in the SAME file creation. If no existing category fits, ADD the new category
  to BOTH the enum in `## Tag schema & vocabulary` AND (if it is `provable`) a battery row in
  `## Grep battery` — update `_header.md` in the same session.
- Every new entry is BORN WITH A `**Design default:**` LINE: a single imperative, author-facing
  sentence placed after the markdown table (preceded by one blank line) is written in the SAME file
  creation. No entry lands detector-only — the generative twin is mandatory at birth.
- Until an entry is tagged, it FLOORS (always deep-checked) by the keystone rule in SKILL.md — so a
  newly-written, not-yet-tagged entry is never silently skipped. The growth race cannot produce a
  silent skip.
