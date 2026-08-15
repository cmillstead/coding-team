# User-Facing Translation

> Read this at the moment you are about to write a reply to the user.
> It binds the ORCHESTRATOR's user-facing reporting step. Nothing else.

## Both halves are required

A skill decides WHAT fields a report must contain. The user's active output
style decides HOW those fields read. You owe the user both, on every reply —
tool-call or not.

1. **Keep every field the skill requires.** Dropping one to sound simpler is a
   violation, not compliance.
2. **Translate the wording into the active output style's voice.** Keeping the
   field but pasting the agent's phrasing is also a violation.

Complete but unreadable fails. Readable but missing a field fails.

## What counts as raw material

Subagent reports, review verdicts, severity codes, hook errors, and tool
output are INPUT. They are never reply text. If your reply still carries their
jargon — severity codes, verdict words, audit-speak — you skipped this step.

## Keep these exact

Paths, commands, error strings, and version numbers are copied VERBATIM.
Translate the prose around them, never the artifact itself. When a raw log is
the thing the user must act on, show it and label it in plain words. A block a
skill instructs you to print VERBATIM stays verbatim.

## The rationalization that precedes every violation

"This user is technical, they can handle the dense version."

When you catch yourself thinking it, that IS the signal you are about to skip
translating. Don't.

> The quoted sentence above also appears in the active output-style file and
> in `~/.claude/CLAUDE.md` — reword all three together.

## Out of scope

Worker agents keep producing dense structured reports in their own format —
that output is INPUT to this step, never output from it. Do NOT add this rule
to `agents/*.md`; it would corrupt the report formats the pipeline parses.

This binds the CHAT REPLY only. When the same report is also written to a file
or parsed by a later phase, the written artifact keeps the skill's format.
