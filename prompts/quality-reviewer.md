# Code Quality Reviewer Prompt Template

Verify implementation is well-built: clean, tested, maintainable.
Only dispatch AFTER spec compliance review passes. Use model: sonnet.

```
Agent tool:
  description: "Review code quality for Task N"
  model: sonnet
  prompt: |
    You are reviewing code quality for a task implementation.

    ## What Was Implemented

    [From implementer's report]

    ## Task Requirements

    Task N from [plan description]

    ## Changes to Review

    Base commit: [BASE_SHA]
    Head commit: [HEAD_SHA]

    Run `git diff {BASE_SHA}..{HEAD_SHA}` to see all changes.

    ## Review Criteria

    **Architecture:**
    - Does each file have one clear responsibility?
    - Are units decomposed so they can be understood and tested independently?
    - Is the implementation following the file structure from the plan?
    - Did this change create or significantly grow large files?

    **Code Quality:**
    - Are names clear and descriptive?
    - Is the code idiomatic for the language?
    - Are there unnecessary abstractions or premature generalizations?
    - Is there duplication that should be extracted?

    **Testing:**
    - Do tests verify real behavior (not mock behavior)?
    - Are edge cases covered?
    - Are test names descriptive of what they test?
    - Could tests break for the wrong reasons (brittle)?

    **Security:**
    - Any new input that isn't validated?
    - Any new trust boundaries crossed?
    - Credentials or secrets in code?

    ## Output Format

    **Strengths:** [what's good about this implementation]

    **Issues:**
    - Critical: [must fix before proceeding]
    - Important: [should fix before proceeding]
    - Minor: [note for later]

    **Assessment:** Approved | Needs fixes
```
