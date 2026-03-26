---
name: Spec clarity rationalization for self-execution
description: Orchestrator offers self-execution as option when spec is clear; spec clarity should determine model tier not delegation
type: feedback
---

Orchestrator asks "should I just execute them directly since the spec is already clear?" — presenting self-execution as a valid option alongside delegation.

**Why:** The existing prohibition covers *doing* self-execution but doesn't cover *offering* it as an option. The rationalization "spec is already clear" is a new variant distinct from "doc-level edits" and "mechanical changes."

**How to apply:** Spec clarity determines model tier (haiku for clear specs, sonnet for judgment), not whether to delegate. All code changes go through Agent tool regardless of spec clarity. The orchestrator should present a plan and delegate — never offer "I'll do it myself" as one of the options. Named rationalization added to SKILL.md Red Flags and consolidated-feedback rule 16.
