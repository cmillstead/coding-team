---
name: PreToolUse/PostToolUse hook dispatcher consolidation
description: Per-tool PreToolUse and PostToolUse settings.json entries consolidated into pretooluse-dispatcher.py and posttooluse-dispatcher.py, extending the existing session-start-dispatcher/prompt-dispatcher pattern to tool-use events
type: project
---

## Context
Individual hooks (write-guard, git-safety-guard, rtk, loop-detection, lint-warning-enforcer, codesight-hooks, builder-self-check, coding-team-lifecycle) were each registered as separate PreToolUse/PostToolUse entries in `settings.json`, matched per tool_name. This mirrored the pre-consolidation state of SessionStart hooks (6 separate hooks, later folded into one dispatcher per `29eab28`). Multiple handlers firing on the same event (e.g. Bash PostToolUse running both loop-detection and lint-warning-enforcer) needed a defined output-merging contract that didn't exist while each was independently registered.

## Decision
Added `hooks/pretooluse-dispatcher.py` and `hooks/posttooluse-dispatcher.py` (PR #101, commit `c4c2c52`, 2026-06-25; hardened by PR #102, commit `cf38533`, same day) as single `matcher=""` settings.json entries that route internally by `tool_name`, replacing N per-tool entries with 2 dispatcher entries.

Key invariants preserved verbatim:
- write-guard and git-safety-guard's BLOCKING contract (subprocess, verbatim stdout + exit code passthrough).
- `rtk hook claude` still runs for Bash PreToolUse via subprocess.
- codesight usage logging continues for `mcp__codesight__query`.

Output-merging contract for PostToolUse (finalized in the PR #102 hardening pass):
1. Handlers run in registration order.
2. **Exit-code-2 block (mechanism b):** if a handler exits 2, its stderr is written to real stderr and the dispatcher exits 2 immediately — first such handler wins, no further handlers run. This is a new case PR #101's first cut missed (only handled stdout-JSON blocks); PR #102 fixed it (`cf38533`) after discovering `if stdout.strip():` silently dropped exit-2-only handlers.
3. **Stdout-JSON block (mechanism a):** `{"decision":"block","reason":"..."}` — collected across ALL handlers (they all still run), merged into one block response.
4. **Advisories:** `{"decision":"allow","reason":"..."}` — merged, reasons joined by double-newline.
5. All-silent → exit 0, no output.

Escape hatches: `CT_PRETOOLUSE_DISPATCHER_DISABLE`/`SKIP` and `CT_POSTTOOLUSE_DISPATCHER_DISABLE`/`SKIP`.

## Alternatives Considered
- **Leave per-tool registration as-is** — rejected: N settings.json entries per event type is the same maintenance/drift surface the SessionStart consolidation (`29eab28`) already fixed for a different event type; leaving PreToolUse/PostToolUse un-consolidated was an inconsistency, not a deliberate choice.
- **`stdout.strip()`-only propagation** (PR #101 original) — rejected after PR #102 found it dropped exit-2 (stderr-only) handler blocks silently. Fixed to `if stdout.strip() or rc != 0:`.

## Constraints
- `scripts/deploy.sh`'s hook-registration verifier (see deploy-script-symlinks decision) must count a hook as "registered" if its name appears in `settings.json` OR either dispatcher file — this was already true for the SessionStart/UserPromptSubmit dispatchers (D198) and needed no further change for the Tool-use dispatchers since the verifier greps dispatcher file contents generically.

## Consequences
- **Memory unit-counting impact:** `memory/feedback-hook-accumulation.md` predates this change and counts hooks by settings.json entry; that counting unit is now wrong (4 dispatchers — session-start, prompt, pretooluse, posttooluse — route to N internal checks each, so "number of settings.json entries" undercounts real hook logic). See the feedback file's update / superseding note.
- New PreToolUse or PostToolUse hooks are added by registering inside the relevant dispatcher's routing table, not by adding a new settings.json entry — routing logic lives in `hooks/pretooluse-dispatcher.py` / `hooks/posttooluse-dispatcher.py`.
