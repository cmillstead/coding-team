# Process Rules — Enforcement Design (on-demand reference)

The gate lines in `phases/planning.md`, `phases/audit-loop.md`, and `phases/execution.md` are
compact imperatives. This file holds their bodies, failure examples, and the two supporting
mechanisms (decision-memo format, proportionality exemption). Narrative and origin story:
vault note `by-construction-over-policing`.

Origin: the local-lora-pipeline M2.0 verification-wall saga — 9 paper-review passes rediscovered a
single flaw class ("works if someone remembers to declare it") at 9 successive floors. Each pass
caught a real would-be-Critical at ~1/10 the cost of a full code review, but 4 of the 9 were
avoidable with these rules in place up front. The rules push the catch earlier — into planning and
triage — instead of re-discovering the same generator at every floor.

## The six process rules

1. **Inventory before estimate.** No scope label ("mechanical", "small", "broad") without a
   grep/AST site inventory linked in the plan. An estimate without an inventory is a vibe with a
   word attached. *(Prevented failure: a "mechanical move" grew 3× because nobody enumerated the
   touch points first.)*

2. **Prototype the falsifier.** Any "the test/guard shall verify X" sentence in a plan or spec
   ships with a throwaway spike proving the check is computable against the real codebase, BEFORE
   the rule freezes. Unbuildable rules otherwise get frozen, cited, then un-ratified at ceremony
   cost. *(Prevented failure: a frozen source-scan rule caught 2 of N sites when finally run; two
   models had to prove it undecidable.)*

3. **Hunt the generator.** The **second** finding that rhymes with a prior one (same shape,
   different site) STOPS instance-fixing; name the generating class before continuing, then sweep
   for every instance of that class. Upstream twin of the existing "pattern-sweep not list-fix"
   review rule. *(Prevented failure: declare-it-yourself was fixed six times at six floors before
   anyone named it.)*

4. **Pre-commit stop-lines.** Before entering any review loop — the harness-defined ones (the Plan
   Review Loop and the audit loop) count, not only custom loops — write down which finding-type
   ends the loop and what happens then (who rules, what gets escalated). Decided before pass 1,
   honored when tripped. *(This one already worked: both armed wires fired and ended loops that
   would otherwise have drifted.)*

5. **Paper before code for structural components.** Enforcement layers, walls, gates, and trust
   boundaries get design-sheet review (cross-model) BEFORE implementation. Ordinary features don't.
   The tell: if the component's job is to constrain other code, it's structural.

6. **Construction over policing.** Prefer deleting the possibility (private module, API deletion,
   directory ownership, keys-not-paths) over detecting the violation. Falsifiers must be decidable —
   no judgment calls ("safe vs unsafe file") inside a test; if a test needs judgment, change the
   code layout until it doesn't.

Plus one interpretive rule:

**Purpose over letter.** When a frozen rule proves unbuildable, identify the rule's PURPOSE, satisfy
it by other mechanical means, and log the amendment. Don't waive it, and don't pretend the letter
still holds.

## Two-model agreement (advisory heuristic — not one of the six)

Two-model agreement on a structural finding = treat it as real. A single-model structural finding
gets a verification step before anyone acts on it. This is a confidence heuristic, not a gate — no
phase file carries it as a line.

## Decision-memo format (how a ruling is requested)

When the pipeline surfaces a finding, defer, or scope question to the user (or an advisor/architect
session) for a ruling, write it as a repo file, not a paraphrase in a chat message. The request
message is one line pointing at the file. The memo carries:

- **Options** — the real choices, each stated plainly.
- **Recommendation** — which one, and why, in one or two sentences.
- **Verified evidence** — checked against the ACTUAL code, not memory (cite file:line).
- **What was already ruled** — prior decisions this builds on, so the advisor doesn't re-litigate.

The advisor reads the primary artifact, never a summary of it.

## Proportionality exemption (a ruled decision, not a gap)

The skip-path pre-flight (in `phases/execution.md`) and the planning gates do NOT apply to the
trivial path: a single-file change of ≤20 lines routed directly to Phase 5. The overhead of
inventory, falsifier spikes, and stop-lines isn't justified at that size. This exemption is a
deliberate decision, recorded here so it reads as ruled rather than forgotten.

## Related

- `by-construction-over-policing` (vault) — the narrative these rules come from.
- `structural-theses-stay-in-cross-model-review` (vault) — the sibling spike rule already in
  patterns (rule 2 is its planning-phase twin).
