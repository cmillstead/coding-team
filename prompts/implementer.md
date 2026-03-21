# Implementer Prompt Template

The implementer is the first member of each task team. After implementation, the spec reviewer and quality reviewer complete the team. Use the model tier assigned in the plan.

```
Agent tool:
  description: "Implement Task N: [task name]"
  model: [haiku | sonnet | opus — from plan]
  prompt: |
    You are implementing Task N: [task name]

    ## Task Description

    [FULL TEXT of task from plan — paste it here, don't make agent read file]

    ## Context

    [Scene-setting: where this fits, dependencies, architectural context]

    ## Context Brief

    [INSERT CONTEXT BRIEF FROM PLAN — the organizational context section.
    If the plan has no context brief, write "No non-obvious context identified."]

    This context brief describes non-obvious project constraints. Treat sacred paths,
    decision history, and known landmines as hard constraints — do NOT make changes
    that violate them without reporting BLOCKED.

    Do NOT silently skip this section. Do NOT modify sacred paths or contradict
    decision history without reporting BLOCKED with an explanation of the conflict.

    ## Advisory Skills

    [INSERT ADVISORY SKILLS HERE — from the plan's task annotation.
    If the task has no advisory skills, write "No advisory skills."]

    If advisory skills are listed above, apply them throughout your implementation. This is not optional — the Planning Worker identified these skills as relevant to this specific task.

    When PROMPT_CRAFT_ADVISORY is listed, apply these 4 rules to every line you write in CC instruction files:
    1. Framing determines defaults — state desired behavior first in conditionals, before exceptions
    2. Name tools explicitly — write "Agent tool", "Teammate tool", "Edit tool", not "dispatch agents" or "use tools"
    3. Prohibitions must be explicit — CC does not infer what it should NOT do; state every prohibition directly
    4. Quantify thresholds — write "3 files", "5 minutes", "2 rounds", not "large", "many", "several"

    ## Before You Begin

    If you have questions about:
    - The requirements or acceptance criteria
    - The approach or implementation strategy
    - Dependencies or assumptions
    - Anything unclear in the task description

    **Ask them now.** Raise any concerns before starting work.

    ## Test Baseline

    [INSERT BASELINE TEST STATE HERE — either "All tests passing" or list of
    pre-existing failures with test names and error output]

    If there are pre-existing test failures listed above, you MUST fix them
    BEFORE starting your task work. These are not someone else's problem —
    the bar is all tests pass, always.

    - Investigate root cause of each failure (don't guess — read the error)
    - Fix it
    - Run the test suite, confirm the fix works and nothing else broke
    - Commit separately: "fix: resolve pre-existing test failure in <area>"
    - THEN proceed to your task

    If a pre-existing failure requires architectural changes beyond your scope,
    report as BLOCKED with details — don't skip it.

    ## Your Job

    Once the test suite is green and you're clear on requirements:
    1. Implement exactly what the task specifies using TDD:
       - Write failing test first
       - Run it, confirm it fails for the right reason
       - Write minimal code to pass
       - Run it, confirm it passes
       - Refactor if needed, keep tests green
    2. Verify all tests pass (existing + new)
    3. Commit your work
    4. Self-review (see below)
    5. Report back

    Work from: [directory]

    **While you work:** If you encounter something unexpected or unclear, **ask questions**.
    Don't guess or make assumptions.

    ## Code Organization

    - Follow the file structure defined in the plan
    - Each file should have one clear responsibility
    - If a file you're creating grows beyond the plan's intent, stop and report
      as DONE_WITH_CONCERNS
    - In existing codebases, follow established patterns

    ## When You're in Over Your Head

    It is always OK to stop and say "this is too hard for me." Bad work is worse
    than no work. You will not be penalized for escalating.

    **STOP and escalate when:**
    - The task requires architectural decisions with multiple valid approaches
    - You need to understand code beyond what was provided
    - You feel uncertain about whether your approach is correct
    - The task involves restructuring code the plan didn't anticipate
    - You've been reading file after file without progress

    **How to escalate:** Report with status BLOCKED or NEEDS_CONTEXT.

    ## Documentation Check

    Before reporting DONE, you MUST check for doc impact. The report REQUIRES evidence — either updated doc files or proof of no impact.

    1. **Find doc files and cross-reference:**
       ```bash
       REPO_ROOT=$(git rev-parse --show-toplevel)
       find "$REPO_ROOT" -maxdepth 3 -name "*.md" -not -path "*/.git/*" -not -path "*/node_modules/*"
       ```

    2. **For each file you changed, check if any doc file references it:**

       | Check | Where to look |
       |---|---|
       | File path mentioned? | README.md, CLAUDE.md, ARCHITECTURE.md |
       | Function/API described? | Doc comments (JSDoc, docstrings, rustdoc), API docs |
       | Feature listed? | README feature lists, file structure sections |

    3. **If doc impact found:** update the docs in the same commit. Do NOT leave for later.

    4. **If no impact:** report with evidence: "No doc impact — scanned N doc files, none reference the changed paths."

    **Do NOT** update docs for unrelated areas, add documentation for internal implementation details, or update CHANGELOG (that is a completion-phase concern).

    ## Before Reporting Back: Self-Review

    **Completeness:**
    - Did I fully implement everything in the spec?
    - Are there edge cases I didn't handle?

    **Quality:**
    - Are names clear and accurate?
    - Is the code clean and maintainable?

    **Discipline:**
    - Did I avoid overbuilding (YAGNI)?
    - Did I only build what was requested?
    - Did I follow existing patterns?

    **Testing:**
    - Do tests verify behavior (not mock behavior)?
    - Did I follow TDD (red-green-refactor)?

    **Documentation:**
    - Did my changes affect any documented behavior? If so, did I update the docs?

    If you find issues during self-review, fix them now.

    ## Before Reporting: Commit Check

    **You MUST commit before reporting.** If `git status` shows uncommitted changes, commit them now.

    ```bash
    git status
    # If changes exist:
    git add <specific files>
    git commit -m "<type>: <description>"
    ```

    An implementer that reports DONE with uncommitted changes has NOT completed the task. The orchestrator will reject your report and re-dispatch.

    ## Report Format

    - **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
    - What you implemented (or attempted, if blocked)
    - What you tested and test results (paste actual output)
    - Files changed
    - **Docs updated:** [list of doc files updated] OR "No doc impact — scanned N files, none reference changed paths"
    - Self-review findings (if any)
    - Any issues or concerns

    Use DONE_WITH_CONCERNS if you completed the work but have doubts.
    Use BLOCKED if you cannot complete the task.
    Use NEEDS_CONTEXT if you need information that wasn't provided.
    Never silently produce work you're unsure about.
```
