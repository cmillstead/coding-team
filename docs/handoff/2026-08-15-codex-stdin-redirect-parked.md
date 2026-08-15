# Handoff — codex exec stdin hang fix (COMPLETE, self-contained)

**Date:** 2026-08-15
**Repo:** `skills/coding-team` ONLY. Nothing here touches `~/.claude`.
**Status:** 6 of 8 fixes applied. 2 blocked on a plan-arm conflict, not on anything technical.

This file is deliberately self-contained. The plan it came from lives at `docs/plans/2026-08-14-codex-stdin-redirect.md`, but **`docs/plans/` is gitignored (`.gitignore:2`) so that file is untracked and may vanish.** Everything you need is reproduced below. You do not need the plan.

---

## 1. The bug

`codex exec` hangs forever when given a prompt ARGUMENT while stdin is left open.

`codex exec --help` (codex-cli 0.144.5) documents the PROMPT argument as:

> "If not provided as an argument (or if `-` is used), instructions are read from stdin. If stdin is piped and a prompt is also provided, stdin is appended as a `<stdin>` block."

So codex drains stdin looking for more input and blocks on an EOF that never arrives. In a terminal a human presses Ctrl-D. A tool-invoked run has nobody to do that.

Evidence from two real sessions:
- output file contained exactly `Reading additional input from stdin...`
- 0.03 seconds of CPU across 3 hours 19 minutes — blocked, not thinking
- the same prompt with `< /dev/null` returned in seconds

## 2. The fix, and the trap

```bash
codex exec "..." < /dev/null 2>&1 | tee f    # CORRECT — binds to codex
codex exec "..." 2>&1 | tee f < /dev/null    # BROKEN — binds to tee, still hangs
```

The shell binds a redirect to the **nearest command in its pipe stage**. Put `< /dev/null` immediately after the codex arguments and BEFORE `2>&1 |`. Placed after the pipe it belongs to `tee`, and the template looks fixed while still hanging — worse than an obviously missing redirect.

Verified live this session:

```bash
codex exec --sandbox read-only "Reply with exactly the word PONG and nothing else." < /dev/null 2>&1 | tee /tmp/codex-shape-test.txt
```
Returned `PONG` in seconds, 582 bytes captured.

**The invariant is "stdin is BOUND", not "`/dev/null` is present."** Two other forms are equally safe because both reach EOF:
- upstream pipe — `git diff main | codex exec "..."`
- prompt from a file — `codex exec ... - <"$FILE"` (as `~/.claude/skills/codex-first/SKILL.md` already does)

**NEVER add `< /dev/null` to those** — it discards the input they exist to send.

## 3. Root cause (why this recurred)

This rule was ALREADY documented as mandatory in four separate memory files, including `~/.claude/projects/-Users-cevin--claude/memory/reference_codex-exec-invocation.md`. It still burned two more sessions.

Memory is read at session start. The command is copied from the template in the skill file at the moment of dispatch. Every `codex exec` template shipped without the redirect, so the template silently overrode the memory every time.

**Fix the artifact that gets copied.** That is why this lands in `reference.md`, not in another memory file.

---

## 4. APPLIED — `skills/second-opinion/reference.md` (UNCOMMITTED)

Six invocations, all now `< /dev/null` before `2>&1 |`. Confirmed by `grep -n "dev/null" skills/second-opinion/reference.md`:

| Line | What |
|---|---|
| 31 | plan-review fenced template |
| 66 | iterative-revision resume fenced template |
| 133 | challenge fenced template |
| 143 | consult fenced template |
| 146 | inline follow-up directive |
| 161 | inline follow-up directive — missed by the original brief, found by the Codex plan gate |

Lines 31 and 66 are byte-identical; they were changed with one `replace_all` edit on the string `  2>&1 | tee /tmp/second-opinion-review-${REVIEW_ID}.txt`.

Line 146 now reads:
```
For follow-ups: `codex exec resume ${CODEX_SESSION_ID} "FOLLOW-UP QUESTION" < /dev/null`
```
Line 161 now reads:
```
For follow-ups, use `codex exec resume ${CODEX_SESSION_ID} "FOLLOW-UP QUESTION" < /dev/null` to maintain conversation context.
```

### If the edits are lost, here is exactly how to redo them

Four fenced templates — the ORIGINAL text of each final line, and what it becomes:

| Line | Original (before) | After |
|---|---|---|
| 31, 66 | `  2>&1 \| tee /tmp/second-opinion-review-${REVIEW_ID}.txt` | `  < /dev/null 2>&1 \| tee /tmp/second-opinion-review-${REVIEW_ID}.txt` |
| 133 | `  2>&1 \| tee /tmp/second-opinion-challenge-${REVIEW_ID}.txt` | `  < /dev/null 2>&1 \| tee /tmp/second-opinion-challenge-${REVIEW_ID}.txt` |
| 143 | `  2>&1 \| tee /tmp/second-opinion-consult-${REVIEW_ID}.txt` | `  < /dev/null 2>&1 \| tee /tmp/second-opinion-consult-${REVIEW_ID}.txt` |

Lines 31 and 66 are byte-identical — one Edit with `replace_all: true`. Both lines are preceded by a backslash continuation, so the joined command becomes `codex exec "..." < /dev/null 2>&1 | tee ...`.

Two inline directives:

| Line | Original (before) | After |
|---|---|---|
| 146 | ``For follow-ups: `codex exec resume ${CODEX_SESSION_ID} "FOLLOW-UP QUESTION"` `` | ``For follow-ups: `codex exec resume ${CODEX_SESSION_ID} "FOLLOW-UP QUESTION" < /dev/null` `` |
| 161 | ``For follow-ups, use `codex exec resume ${CODEX_SESSION_ID}` to maintain conversation context.`` | ``For follow-ups, use `codex exec resume ${CODEX_SESSION_ID} "FOLLOW-UP QUESTION" < /dev/null` to maintain conversation context.`` |

### CURRENT GIT STATE — READ BEFORE COMMITTING ANYTHING

As of 2026-08-15, in this shared checkout:

- **Branch is `fix/trk-136-git-global-options` — that belongs to a DIFFERENT session, not to this work.**
- `skills/second-opinion/reference.md` — the six edits, **modified and UNCOMMITTED**.
- `docs/handoff/2026-08-15-codex-stdin-redirect-parked.md` — this file, **UNTRACKED**. A tree clean would delete it.
- `hooks/_lib/git.py`, `hooks/tests/test_lib.py` — the other session's TRK-136 work, modified and uncommitted. **Not yours. Do not stage, stash, or revert them.**

**Do NOT commit onto the current branch.** It was tried once this session and reverted (`git reset HEAD~1`) because it puts this fix into TRK-136's history. The fix needs its own branch off `origin/main`, but **creating one moves the shared working tree and yanks the other session** — so branch only when that session is closed or has agreed.

When the checkout is yours alone, stage explicit paths and nothing else. **Never `git add -A` here.**

```bash
git add skills/second-opinion/reference.md docs/handoff/2026-08-15-codex-stdin-redirect-parked.md
git commit -m "fix(second-opinion): bind stdin on every codex exec template

codex exec drains stdin even when a prompt arg is supplied, so a
tool-invoked run blocks forever waiting for an EOF that never comes
(observed: 0.03s CPU over 3h19m). Add < /dev/null immediately after the
codex args and before 2>&1 | on all six reference.md invocations."
```

A pre-commit hook in this repo requires lint/tests to have been run before any commit. It also pattern-matches the literal text `git commit` inside ANY bash command, so a plain `grep` for that string trips it — that is a known false positive, not a real block.

### Also written this session (coding-team memory, already on disk)

- `feedback_rule-must-live-in-the-copied-template.md` — a rule kept only in memory keeps recurring; it has to go in the template that gets copied. This is the generalized lesson from this bug.
- `feedback_read-the-design-memory-before-structural-choices.md` — open the named `project_*` memory before choosing worktree/branch/plan-arming.
- `feedback_session-root-is-the-scope-boundary.md` — the session's start directory is a hard scope; never run shared-checkout git commands.

---

## 5. REMAINING ITEM 1 — `skills/second-opinion/SKILL.md`

The `## Rules` bullet (currently line 189) names a command with no redirect. **Change the backticked span only** — the file is EXACTLY 200 lines and `hooks/hook-health-check.py:255` warns above 200, citing the finding that MANDATORY labels stop working past that length.

From:
```
- Reuse Codex session ID for multi-round reviews via `codex exec resume SESSION_ID`
```
To:
```
- Reuse Codex session ID for multi-round reviews via `codex exec resume SESSION_ID "FOLLOW-UP" < /dev/null`
```

Verify after: `wc -l skills/second-opinion/SKILL.md` must still print `200`.

### Optional, higher value — the rule at the dispatch boundary

Templates get paraphrased, so the template alone is necessary but not sufficient. If you want the durable version, insert this as ONE line after line 100 (the end of the `Pre-flight — MANDATORY` section, which is the last thing read before any codex call and the only spot reachable from review, challenge AND consult). To stay at 200 lines, delete line 108 (`Always capture output: ...`) and its trailing blank at 109 — its content is carried below.

```
**MANDATORY — capture every Codex run, and bind stdin on every `codex exec`.** Capture ALL Codex output, `review` included: `2>&1 | tee /tmp/second-opinion-<mode>-${REVIEW_ID}.txt`. For `codex exec` and `codex exec resume`, stdin MUST ALSO be explicitly bound — unbound, codex drains an stdin that never reaches EOF, prints `Reading additional input from stdin...`, and hangs forever (observed: 3h19m at 0.03s CPU). An argument-prompt invocation binds it with `< /dev/null` placed immediately after the codex arguments and BEFORE `2>&1 |`. NEVER put the redirect after the pipe (`... 2>&1 | tee file < /dev/null`) — the shell binds it to `tee` and codex still hangs. When you are DELIBERATELY feeding codex finite input, stdin is ALREADY bound — NEVER add `< /dev/null` to those, it would discard the input; write them in full as `git diff main | codex exec "..." 2>&1 | tee /tmp/second-opinion-<mode>-${REVIEW_ID}.txt`. `codex review` with an argument prompt does not read stdin and needs no redirect (`codex review -` does read stdin by design). Known rationalizations, both bypasses: "it's a quick one-off, not the full template" (the hang does not care) and "I'm running it in the foreground so I can Ctrl-D" (a tool-invoked run has no human at the keyboard).
```

---

## 6. REMAINING ITEM 2 — the guard test

Create `hooks/tests/test_codex_stdin_redirect.py`. Full source, ready to paste:

```python
"""Guard: every `codex exec` template in the second-opinion skill binds stdin.

`codex exec` with a prompt ARGUMENT still drains stdin. `codex exec --help`
(codex-cli 0.144.5) documents the PROMPT argument as: "If not provided as an
argument (or if `-` is used), instructions are read from stdin. If stdin is
piped and a prompt is also provided, stdin is appended as a `<stdin>` block."
A tool-invoked run inherits an stdin that never reaches EOF, so codex prints
"Reading additional input from stdin..." and blocks forever. Observed twice in
real sessions: 0.03s of CPU across 3h19m.

The redirect MUST bind to codex, not to the pipe tail:

    codex exec "..." < /dev/null 2>&1 | tee f   # correct - binds to codex
    codex exec "..." 2>&1 | tee f < /dev/null   # BROKEN - binds to tee

`codex review` (the SUBCOMMAND) is deliberately NOT covered. It reads stdin
only when `-` is passed and carries no stdin-appending clause. Do NOT widen
the scan to it.

The invariant is "stdin is explicitly BOUND", NOT "`/dev/null` is present".
An upstream pipe and a `- <file` prompt redirect are equally safe. Appending
`< /dev/null` to those DISCARDS their input. If a new safe binding appears,
EXTEND `_stdin_is_bound` rather than deleting a test.

Known rationalization: "the template is just an example, not a real command" -
NO. Every fenced template in reference.md is copied verbatim by an agent at
dispatch time. That is what makes it a hang vector.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]  # tests/ -> hooks/ -> repo root
SECOND_OPINION = REPO_ROOT / "skills" / "second-opinion"
SCANNED_FILES = (SECOND_OPINION / "reference.md", SECOND_OPINION / "SKILL.md")

FENCE_RE = re.compile(r"^```(?:bash|sh)\n(.*?)^```", re.MULTILINE | re.DOTALL)
INLINE_SPAN_RE = re.compile(r"`([^`\n]*codex exec[^`\n]*)`")
SUBCOMMAND_RE = re.compile(r"codex\s+exec\b")
QUOTED_ARG_RE = re.compile(r'"[^"]*"', re.DOTALL)
# Flags that print and exit. They accept no prompt and read no stdin, so a
# doc citing `codex exec --help` as evidence is not a hang vector.
INFO_FLAGS = frozenset({"--help", "-h", "--version", "-V"})
DEV_NULL_RE = re.compile(r"<\s*/dev/null")
PIPELINE_ANCHOR = "2>&1"
DASH_STDIN_RE = re.compile(r"(?:^|\s)-\s*<")
SEGMENT_SEPARATORS = ("&&", "||", ";")


def _codex_segment(command: str) -> str:
    """The shell segment that actually runs codex, with quoted args removed.

    Scoping is load-bearing. A naive whole-string search for `/dev/null`
    accepts all of these, none of which binds CODEX's stdin:

        echo x < /dev/null && codex exec "review" 2>&1 | tee f
        codex exec "mention < /dev/null in the prompt" 2>&1 | tee f
        codex exec "review" 2>&1 | tee f < /dev/null
    """
    segment = QUOTED_ARG_RE.sub('"PROMPT"', command)
    for separator in SEGMENT_SEPARATORS:
        parts = segment.split(separator)
        segment = next(
            (part for part in parts if SUBCOMMAND_RE.search(part)), parts[-1]
        )
    return segment


def _stdin_is_bound(command: str) -> bool:
    """True when CODEX's own stdin is explicitly bound by a safe form.

    Binding is judged on codex's OWN pipeline stage. A redirect in a later
    stage belongs to that stage's command (`tee`), never to codex.
    """
    segment = _codex_segment(command)
    stages = segment.split("|")
    for index, stage in enumerate(stages):
        if not SUBCOMMAND_RE.search(stage):
            continue
        if index > 0:
            return True  # an upstream stage pipes finite input into codex
        return bool(DEV_NULL_RE.search(stage) or DASH_STDIN_RE.search(stage))
    return False


def _redirect_precedes_pipeline(command: str) -> bool:
    """True when a `< /dev/null` redirect, if present, sits before the pipe.

    Narrower than _stdin_is_bound: it gives the SPECIFIC diagnostic "wrong
    side of the pipe" instead of the generic "stdin is unbound".
    """
    unquoted = QUOTED_ARG_RE.sub('"PROMPT"', command)
    match = DEV_NULL_RE.search(unquoted)
    if match is None:
        return True
    anchor = unquoted.find(PIPELINE_ANCHOR)
    if anchor == -1:
        anchor = unquoted.find("|")
    return anchor == -1 or match.start() < anchor


def _logical_commands(script: str) -> list[str]:
    """Split a fenced block into logical shell commands.

    Quoted spans are placeholdered FIRST (prompt args contain raw newlines),
    then backslash-continued lines are joined.
    """
    without_prompts = QUOTED_ARG_RE.sub('"PROMPT"', script)
    joined = re.sub(r"\\\n\s*", " ", without_prompts)
    return [line.strip() for line in joined.splitlines() if line.strip()]


def _fenced_codex_exec_commands() -> list[tuple[str, str]]:
    """Every logical `codex exec` command inside a fenced bash block."""
    found = []
    for path in SCANNED_FILES:
        for block in FENCE_RE.findall(path.read_text()):
            for command in _logical_commands(block):
                if "codex exec" in command:
                    found.append((path.name, command))
    return found


def _is_invocation(span: str) -> bool:
    """True when an inline span INVOKES codex exec rather than naming it.

    Anything following the subcommand makes it an invocation:
    `codex exec resume ${CODEX_SESSION_ID}` is a template an agent copies.
    A bare `codex exec` or `codex exec resume` is prose.

    Rejected heuristic, recorded so it is not reintroduced: "a span is an
    invocation iff it contains a double quote." That misses every
    placeholder-argument directive, which is exactly the copied form.
    """
    match = SUBCOMMAND_RE.search(span)
    if match is None:
        return False
    tail = span[match.end():].strip()
    if tail.startswith("resume"):
        tail = tail[len("resume"):].strip()
    if tail in INFO_FLAGS:
        return False  # `codex exec --help` prints and exits; it reads no stdin
    return bool(tail)


def _inline_codex_exec_invocations() -> list[tuple[str, str]]:
    """Every inline backticked span that INVOKES codex exec."""
    found = []
    for path in SCANNED_FILES:
        for span in INLINE_SPAN_RE.findall(path.read_text()):
            if _is_invocation(span):
                found.append((path.name, span))
    return found


def _all_codex_exec_commands() -> list[tuple[str, str]]:
    """Fenced templates and inline invocations together."""
    return _fenced_codex_exec_commands() + _inline_codex_exec_invocations()


def test_every_codex_exec_binds_stdin():
    """Every `codex exec` template and inline invocation must bind stdin."""
    offenders = [
        f"{name}: {command}"
        for name, command in _all_codex_exec_commands()
        if not _stdin_is_bound(command)
    ]
    assert not offenders, (
        "codex exec invocation(s) do not bind stdin. For an argument-prompt "
        "invocation add `< /dev/null` immediately after the codex arguments "
        "and BEFORE `2>&1 |`. Do NOT add `/dev/null` to a command that is "
        "deliberately being fed a pipe or a file - that would discard its "
        "input; bind it to that finite source instead:\n" + "\n".join(offenders)
    )


def test_stdin_redirect_precedes_the_pipeline():
    """`< /dev/null` must come BEFORE `2>&1 |`, not after the pipe."""
    offenders = [
        f"{name}: {command}"
        for name, command in _all_codex_exec_commands()
        if not _redirect_precedes_pipeline(command)
    ]
    assert not offenders, (
        "`< /dev/null` appears AFTER `2>&1 |`. The shell binds a redirect to "
        "the NEAREST command in the pipe stage, so this binds to `tee` and "
        "codex still hangs:\n" + "\n".join(offenders)
    )


def test_safe_finite_stdin_forms_are_not_flagged():
    """The legitimate finite-stdin forms must PASS, not be 'fixed'.

    This is the guard on the guard. Without it, a future tightening would
    start flagging correct commands and the documented remedy ("add
    `< /dev/null`") would silently destroy their input.
    """
    # The three safe bindings must all PASS.
    assert _stdin_is_bound('git diff main | codex exec "review this"')
    assert _stdin_is_bound('codex exec -o /tmp/out.md - <"$PROMPT_FILE"')
    assert _stdin_is_bound('codex exec "review this" < /dev/null 2>&1 | tee f')

    # An unbound command must FAIL.
    assert not _stdin_is_bound('codex exec "review this" 2>&1 | tee f')

    # A redirect belonging to some OTHER command must NOT count as a binding.
    assert not _stdin_is_bound('echo x < /dev/null && codex exec "r" 2>&1')
    assert not _stdin_is_bound('codex exec "mention < /dev/null here" 2>&1')
    assert not _stdin_is_bound('codex exec "r" 2>&1 | tee f < /dev/null')
    assert not _stdin_is_bound('codex exec "r" 2>&1 | cat - </tmp/x')

    # Placement gives the precise "wrong side of the pipe" diagnostic.
    assert not _redirect_precedes_pipeline(
        'codex exec "x" 2>&1 | tee f < /dev/null'
    )
    assert _redirect_precedes_pipeline('codex exec "says < /dev/null" 2>&1')


def test_prose_mentions_are_not_treated_as_invocations():
    """Naming the command is not running it; running it needs a binding."""
    assert not _is_invocation("codex exec")
    assert not _is_invocation("codex exec resume")
    assert not _is_invocation("codex exec --help")
    assert _is_invocation("codex exec resume SESSION_ID")
    assert _is_invocation('codex exec resume ${CODEX_SESSION_ID} "Q"')
    assert _is_invocation('codex exec "review this" < /dev/null')


def test_scan_finds_the_known_invocations():
    """Sanity: the scan must actually find commands, fenced AND inline.

    Without this, a regex that silently stops matching would make every
    assertion above pass on an empty set - a broken instrument reading green.
    """
    fenced = _fenced_codex_exec_commands()
    inline = _inline_codex_exec_invocations()
    assert len(fenced) >= 4, (
        f"expected at least 4 fenced `codex exec` templates under "
        f"{SECOND_OPINION}, found {len(fenced)}. The scan is broken, not the "
        f"templates."
    )
    assert len(inline) >= 3, (
        f"expected at least 3 inline `codex exec` invocations under "
        f"{SECOND_OPINION}, found {len(inline)}. The scan is broken, not the "
        f"templates."
    )

    # Count-independent instrument check. A floor cannot catch a partial
    # regression - the inline inventory legitimately differs before and
    # after the fix. This verifies that EVERY fenced block mentioning
    # codex exec yields at least one logical command, which is what breaks
    # if the quote-stripping or continuation-joining rots.
    for path in SCANNED_FILES:
        for block in FENCE_RE.findall(path.read_text()):
            if "codex exec" not in block:
                continue
            commands = [c for c in _logical_commands(block) if "codex exec" in c]
            assert commands, (
                f"{path.name}: a fenced block contains `codex exec` but "
                f"_logical_commands extracted no command from it. The joiner "
                f"is broken, not the template.\n{block[:200]}"
            )
```

### Expected results

The scanner was run standalone against the real files before and after the fix:

| Run | fenced | inline | unbound | misplaced |
|---|---|---|---|---|
| Before any fix | 4 | 3 | **7** | 0 |
| After all fixes | 4 | 9 | **0** | 0 |

Since `reference.md` is already fixed (6 of the 7), running this test NOW should report exactly **1 offender**: `SKILL.md: codex exec resume SESSION_ID`. Apply section 5 and it goes green.

To prove the placement test is not decorative, temporarily move the consult template's redirect past the pipe (`2>&1 | tee /tmp/second-opinion-consult-${REVIEW_ID}.txt < /dev/null`). BOTH `test_stdin_redirect_precedes_the_pipeline` and `test_every_codex_exec_binds_stdin` should fail. Then revert.

---

## 7. Optional — prose notes for `reference.md`

Not applied. Only worth adding if you want the reasoning to survive in the file itself. Insert after the `## Codex Command Examples` heading:

```markdown
**MANDATORY — every `codex exec` command below binds stdin with `< /dev/null`.**
`codex exec --help` (codex-cli 0.144.5): "If stdin is piped and a prompt is also
provided, stdin is appended as a `<stdin>` block." A tool-invoked run inherits an
stdin that never reaches EOF, so codex prints `Reading additional input from
stdin...` and blocks forever — observed twice, once for 3h19m at 0.03s of CPU.

**Placement is load-bearing.** Put `< /dev/null` immediately after the codex
arguments and BEFORE `2>&1 |`. The shell binds a redirect to the NEAREST command
in its pipe stage, so `... 2>&1 | tee file < /dev/null` binds it to `tee` and
codex still hangs — with a template that now *looks* fixed.

The invariant is that stdin is explicitly BOUND, not that it is always
`/dev/null`. `git diff main | codex exec "..."` and `codex exec ... - <"$FILE"`
are also safe, because both inputs reach EOF — never add `/dev/null` to those.
`codex review` with an argument prompt needs no redirect.
```

---

## 8. Decisions — do not re-litigate

- **No hook.** You were offered a blocking PreToolUse hook that would refuse any `codex exec` missing a redirect, and chose templates-only (lightest durable fix first, `~/.claude/rules/interaction-mandatory.md` rule 2). Escalate to a hook only if the hang recurs after this text fix.
- **`codex review` stays unredirected.** `codex review --help` documents its prompt as "Custom review instructions. If `-` is used, read from stdin" — no stdin-appending clause. Adding a cosmetic redirect teaches that the redirect is boilerplate, which makes it easier to drop where it matters.
- **`codex exec resume` gets the redirect anyway.** Its `--help` also lacks the appending clause, so it may not hang — but a uniform rule is followed correctly far more often than a conditional one.
- **`~/.claude/skills/codex-first/SKILL.md` is already SAFE** (`codex exec ... - <"$P"` — a file reaches EOF). Different repo; do not touch it from a coding-team session.

## 9. Why items 1 and 2 are blocked, and the shared-checkout warning

Both remaining files are behavioral instruction files, so `hooks/write-guard.py` gates them. It allows an instruction-file edit only when the plan currently holding `status: in-progress` declares that path under `instruction_files:`.

The arming plan right now is `docs/plans/2026-08-14-trk-136-git-global-options.md`, which belongs to a **different concurrent session**. Do not disarm another session's plan to get around this. Either do these two edits from that session's context, or wait until TRK-136 reaches `status: complete`.

If you make `docs/plans/2026-08-14-codex-stdin-redirect.md` the armed plan instead, it already declares the right paths:
```yaml
instruction_files: skills/second-opinion/SKILL.md, skills/second-opinion/reference.md, hooks/tests/test_codex_stdin_redirect.py
```
Check `grep -rn "^status: in-progress" docs/plans/` returns nothing before arming anything. Two in-progress plans wedge the guard — it fails closed AND blocks the edit that would unwedge it.

**Shared checkout.** `~/.claude` and this repo share one working tree with other live sessions. **Do not run `git checkout`, `git checkout -b`, `git stash`, or `git commit -A` here** — they hit every session at once. Earlier this session those commands moved another window's branch and stashed its in-flight work. Stage explicit paths only, and check `git status` for foreign dirty files first.

At time of writing `hooks/_lib/git.py` and `hooks/tests/test_lib.py` hold another session's uncommitted TRK-136 work. Leave them alone.

## 10. Review history

The plan behind this went through the Codex gate twice and the plan-doc reviewer once; 10 findings total, all dispositioned. The two that changed the design:

- The first version of the guard test would have flagged the plan's OWN documented finite-stdin examples, so it could never have gone green, and its stated recovery ("fix the example") would have appended `< /dev/null` to a piped command and discarded the diff. Fixed by `_stdin_is_bound` recognizing all three bindings, pinned by `test_safe_finite_stdin_forms_are_not_flagged`.
- The second version judged binding by searching the whole command string, so a redirect belonging to `echo`, to `tee`, or quoted inside a prompt counted as safe. Fixed by `_codex_segment` plus stage-scoped detection; every false-accept case is now a test assertion.
