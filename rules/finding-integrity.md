<!-- This file has NO globs frontmatter on purpose — it is not an auto-load rule.
     It is a dispatch-context include: agent prompts point here and instruct the
     dispatched subagent to read it explicitly before starting, because a
     subagent only reliably sees files it is told to read. -->

# Finding Integrity + BLOCKED Protocol

Canonical text for the two review-agent protocols duplicated across the live
coding-team auditors (ct-spec-reviewer, ct-harden-auditor, ct-simplify-auditor,
ct-qa-reviewer, ct-prompt-craft-auditor, ct-harness-engineer).

## Finding Integrity

"Pre-existing" and "not a regression" are NOT valid reasons to skip a finding.
If the code (or instruction file, or harness component) has a defect —
regardless of when it was introduced — report it. A bug is a bug. Known
rationalization: "this was already there before my changes" — it's still a
finding.

## When You Cannot Complete the Review (BLOCKED)

If you cannot access files, the file list is empty, the spec/plan is missing,
or you encounter content you cannot evaluate:

Report with: **Status: BLOCKED — [reason]**

Do NOT guess, fabricate findings, or return an empty report. A BLOCKED status
is always better than an unreliable review.
