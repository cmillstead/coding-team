---
name: Mandatory Interaction Rules (user-declared)
scope: always-on
---

# Mandatory Interaction Rules

User-declared, MANDATORY on every project. Each was given more than once — do not drop them.

1. **Number either/or choices.** Whenever you present the user a choice between options (either/or
   or multi-option), ALWAYS prefix each option with `1`/`2` (or `a`/`b`) so they can answer with just
   the number/letter. Applies to plain-text questions and AskUserQuestion options alike. Self-check:
   if you are about to write "X or Y?" with no labels, stop and label them.

2. **Don't default to hooks; consolidate.** Hooks are ONE enforcement tool, not the reflex answer for
   every rule. NEVER add a hook per rule — that scales to a million brittle, overlapping hooks. When a
   rule needs promotion past soft memory, FIRST reuse an existing consolidated mechanism (a single
   session-injected rule surface like this file, or one dispatcher-registered injector carrying many
   rules as DATA). Adding a rule should be a one-line data/text edit, not new code. Reuse existing
   injectors; never clone them. Only add a genuinely new mechanism when no existing one can carry the
   rule (e.g. a PreToolUse action-gate — a different verb than inject/inform), and justify it first.
