---
name: Size rationalization bypass
description: Main agent edits code directly by rationalizing individual fixes as "too small" for /coding-team delegation
type: feedback
---

Main agent constructs size-based category exceptions to bypass delegation: "just adding map entries", "just updating test expectations", "just a one-line fix", "mechanical/trivial". Each edit individually seems too small for /coding-team, but delegation rules say "any code, any size."

**Why:** The delegation boundary named what the orchestrator CAN edit (docs) but didn't name the rationalizations used to bypass it. The agent invents a size threshold that doesn't exist in the rules.

**How to apply:** Six named rationalizations added directly below the delegation rule in CLAUDE.md. The rationalizations are: size ("one-line"), category ("map entries", "test expectations"), complexity ("mechanical/trivial"), selectivity ("other fixes need team but not this one"), and file-type ("config not code"). Each one is explicitly rejected as an exemption.
