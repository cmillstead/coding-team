# Ticket: self-modifying write-guard has no safe in-flight edit path

**Status:** UNRESOLVED — this document records the hazard and options; it does not fix it. A decision is needed before it is actioned.

**Date:** 2026-07-25

## Hazard

`~/.claude/hooks/write-guard.py` and `~/.claude/hooks/_lib/` are symlinks into this repo's
`hooks/write-guard.py` and `hooks/_lib/`. The live PreToolUse hook therefore imports the very
files a harness session edits while working on them.

If a partially-applied edit leaves anything on the hook's execution path in a state that raises
(a stale import, an undefined name, a signature mismatch), the top-level exception handler at
the bottom of `hooks/write-guard.py` (`if __name__ == "__main__":` block, `except Exception as exc:`
around lines 959-976) converts that crash into `HOOK CRASH → decision: block`. That blocks
**every** subsequent `Edit`/`Write` call in the repo, for every agent and the orchestrator at
once — not just the one that caused it.

## Why the existing escape hatches don't recover it

`WRITE_GUARD_ALLOW_INSTRUCTION_EDIT=1` is read inside/near `check_phase5()` (around lines
216-344), which only runs if the earlier import/call chain succeeds. Once the module-level
crash is happening, execution never reaches that check. So the documented override cannot
unwedge a crash — it only ever governed a legitimate block, not an error.

The only exits from a wedged state are a hook bypass (forbidden by `rules/hook-bypass.md`) or a
human intervening (e.g. fixing the syntax/name error, or temporarily removing the hook).

## Occurred 3x on 2026-07-25

All three during one plan implementation session. The sharpest instance: a rename landed in one
Edit, and the very next Edit — updating the rename's usage site — was blocked by the crash the
*first* edit had already caused.

## A plain import check is not sufficient

`import _lib.active_plan` succeeding is not proof the module is safe: in the observed case the
stale name was inside a function body, not at import time, so it only raised when that function
was actually called during a real hook invocation. The check that would have caught it is piping
a dummy Edit event through the hook end-to-end and asserting the result is not `HOOK CRASH` —
not a static import check.

## Options to evaluate (not a decision — for the user to weigh)

1. Make the top-level handler fail **open** specifically for `NameError`/`ImportError`
   originating in the guard's own module, with a loud warning. Weakens the fail-closed posture;
   needs its own risk analysis before adoption.
2. Have the hook import from a frozen/deployed copy rather than the live symlink, so in-flight
   edits to the source tree cannot affect the running guard mid-edit.
3. Add a pre-commit/pre-edit syntax-and-smoke gate on `hooks/**` that runs the dummy-event smoke
   test described above before any edit lands.
4. Accept it as-is and rely on stop-and-report (`rules/hook-bypass.md`) — treat the one
   round-trip to the user as the cost of keeping the guard fail-closed.

## Cross-references

- `feedback-self-modifying-hook-wedge` (memory)
- `feedback-ambient-env-corrupts-verification` (memory)
- `rules/hook-bypass.md`
- `phases/named-rationalizations.md` — "Hook bypass" section, "I'm only finishing my own in-flight refactor"
