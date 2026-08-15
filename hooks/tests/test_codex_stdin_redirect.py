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
