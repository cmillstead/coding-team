"""RED-state pin tests for the Phase-boundary entry-step fix (Task 1 of 2).

`phases/*.md` are instruction files an LLM orchestrator reads at runtime.
Two defects exist in the current (pre-fix) content:

- Defect A: each phase-exit file ends by asking the user for a magic phrase
  ("Proceed to Phase N") even though genuine approval already happened
  earlier in the same file -- a redundant second gate where the
  orchestrator parks.
- Defect B: there is no agent-directed step at the boundary at all -- the
  orchestrator has to infer that it should go read the next phase file.

These tests pin the POST-fix state (an explicit "Final step" marker that
directs the orchestrator to read and execute the next phase file, with the
magic-phrase gate removed). They read the real `phases/*.md` files directly
-- no mocks, no tmp_path copies -- and are expected to FAIL until Task 2
lands the fix.
"""

import itertools
import re
from pathlib import Path

import pytest


# name -> (next phase number, file that phase is defined in)
PHASE_EXIT_OWNERS = {
    "dialogue.md": (2, "design-team.md"),
    "design-team.md": (3, "spec-review.md"),
    "spec-review.md": (4, "planning.md"),
    "planning-next-steps.md": (5, "execution.md"),
    "post-execution-review.md": (6, "completion.md"),
}
TERMINAL = "completion.md"
RETURN_OWNERS = {"doc-drift-scan.md": "execution.md"}
DELEGATES = {"planning.md": "planning-next-steps.md", "execution.md": "post-execution-review.md"}

# Gates that must be GONE after Task 2 -- file -> substrings that must NOT appear
REMOVED_GATES = {
    "execution.md": ("Ready to execute?", "On approval, begin execution"),
    "session-resume.md": ("Ready to continue?", "Proceed?"),
}

# Hardcoded on purpose -- NOT computed as a set-difference residual. A
# residual would make test_no_phase_file_is_an_orphan a tautology that can
# never fail.
NON_TRANSITION = (
    "agent-standards.md", "audit-loop.md", "ci-fix-protocol.md",
    "design-team-context-retrieval.md", "design-team-lifecycle.md",
    "execution-reminders.md", "memory-nudge.md", "named-rationalizations.md",
    "plan-format.md", "reference-files.md", "session-resume.md",
    "task-weight.md", "wiki-generation.md", "completion-reference.md",
)

_MAGIC_PHRASE = '"Proceed to Phase'
_TRANSITION_FILES = sorted(
    set(PHASE_EXIT_OWNERS) | {TERMINAL} | set(RETURN_OWNERS) | set(DELEGATES)
)
_STRUCTURAL_LINE = re.compile(r"^(#{1,6} |\d+\. |> )")


def _entry_marker(next_phase: int) -> str:
    return f"**Final step — enter Phase {next_phase}.**"


def _read(phases_dir: Path, filename: str) -> str:
    return (phases_dir / filename).read_text(encoding="utf-8")


def _slice_from_marker(text: str, marker: str, filename: str) -> str:
    """Return text from the marker to EOF. Fails loudly if the marker is absent.

    Used only by tests that require the marker to exist (1b, 4b, 9). Do NOT
    reuse this for test_nothing_structural_follows_entry_step, which must
    pass vacuously pre-fix when no marker is present yet.
    """
    idx = text.find(marker)
    assert idx != -1, f"{filename}: entry-step marker not found: {marker!r}"
    return text[idx:]


@pytest.fixture
def phases_dir(hooks_dir: Path) -> Path:
    """Resolve phases/ the same way conftest.py resolves hooks/ -- via HOOKS_DIR.parent."""
    return hooks_dir.parent / "phases"


class TestExitOwnerEntrySteps:
    @pytest.mark.parametrize("owner_file", sorted(PHASE_EXIT_OWNERS))
    def test_exit_owner_has_entry_step(self, phases_dir, owner_file):
        next_phase, _next_file = PHASE_EXIT_OWNERS[owner_file]
        text = _read(phases_dir, owner_file)
        marker = _entry_marker(next_phase)
        assert marker in text, f"{owner_file}: missing entry-step marker {marker!r}"

    @pytest.mark.parametrize("owner_file", sorted(PHASE_EXIT_OWNERS))
    def test_entry_step_directs_action_at_the_correct_file(self, phases_dir, owner_file):
        next_phase, next_file = PHASE_EXIT_OWNERS[owner_file]
        text = _read(phases_dir, owner_file)
        tail = _slice_from_marker(text, _entry_marker(next_phase), owner_file)
        directive = f"Read `phases/{next_file}` now and execute its first step"
        assert directive in tail, (
            f"{owner_file}: entry step does not direct action at {next_file!r} "
            f"via the single contiguous substring {directive!r}"
        )

    @pytest.mark.parametrize("owner_file", sorted(PHASE_EXIT_OWNERS))
    def test_nothing_structural_follows_entry_step(self, phases_dir, owner_file):
        next_phase, _next_file = PHASE_EXIT_OWNERS[owner_file]
        text = _read(phases_dir, owner_file)
        idx = text.find(_entry_marker(next_phase))
        if idx == -1:
            # Pre-fix state: no marker yet, so vacuously nothing follows it.
            return
        tail_lines = text[idx:].splitlines()[1:]
        for line in tail_lines:
            assert not _STRUCTURAL_LINE.match(line), (
                f"{owner_file}: structural line follows entry-step marker: {line!r}"
            )


class TestTerminalPhase:
    def test_terminal_phase_is_marked_terminal(self, phases_dir):
        text = _read(phases_dir, TERMINAL)
        assert "**Final step — this is the terminal phase.**" in text
        assert "— enter Phase" not in text


class TestReturnOwner:
    def test_return_owner_does_not_jump_to_phase_six(self, phases_dir):
        filename = next(iter(RETURN_OWNERS))
        text = _read(phases_dir, filename)
        assert "proceed to phase" not in text.lower()

    def test_return_owner_resumes_its_caller_without_restarting_it(self, phases_dir):
        filename, caller = next(iter(RETURN_OWNERS.items()))
        text = _read(phases_dir, filename)
        marker = f"**Final step — return to `{caller}`.**"
        assert marker in text, f"{filename}: missing return marker {marker!r}"
        assert "continue from the point that invoked this scan" in text
        assert "execute its first step" not in text


class TestNoMagicPhrase:
    @pytest.mark.parametrize("filename", _TRANSITION_FILES)
    def test_no_transition_file_requests_a_magic_phrase(self, phases_dir, filename):
        text = _read(phases_dir, filename)
        assert _MAGIC_PHRASE not in text, f"{filename}: still requests the magic phrase"


class TestDelegates:
    @pytest.mark.parametrize("delegator, exit_owner", sorted(DELEGATES.items()))
    def test_delegating_phase_points_at_its_exit_owner(self, phases_dir, delegator, exit_owner):
        text = _read(phases_dir, delegator)
        assert exit_owner in text, f"{delegator}: does not name its exit owner {exit_owner!r}"


class TestOrphanFiles:
    def test_no_phase_file_is_an_orphan(self, phases_dir):
        all_files = sorted(p.name for p in phases_dir.glob("*.md"))
        assert len(all_files) == 23, f"expected 23 phase files, found {len(all_files)}: {all_files}"

        categories = {
            "PHASE_EXIT_OWNERS": set(PHASE_EXIT_OWNERS),
            "TERMINAL": {TERMINAL},
            "RETURN_OWNERS": set(RETURN_OWNERS),
            "DELEGATES": set(DELEGATES),
            "NON_TRANSITION": set(NON_TRANSITION),
        }

        # REMOVED_GATES is deliberately excluded -- it is independent and may
        # overlap any category (execution.md is a delegate AND in
        # REMOVED_GATES; session-resume.md is NON_TRANSITION AND in
        # REMOVED_GATES -- both intentional).
        for (name_a, set_a), (name_b, set_b) in itertools.combinations(categories.items(), 2):
            overlap = set_a & set_b
            assert not overlap, f"{name_a} and {name_b} overlap: {overlap}"

        union = set().union(*categories.values())
        assert union == set(all_files), (
            f"orphaned or missing phase files: {set(all_files) ^ union}"
        )


class TestRemovedGates:
    @pytest.mark.parametrize("filename, gates", sorted(REMOVED_GATES.items()))
    def test_removed_gates_are_gone(self, phases_dir, filename, gates):
        text = _read(phases_dir, filename)
        for gate in gates:
            assert gate not in text, f"{filename}: removed gate still present: {gate!r}"


class TestRoutingGuardsSurvive:
    def test_routing_guards_survive(self, phases_dir):
        dialogue_next, _ = PHASE_EXIT_OWNERS["dialogue.md"]
        dialogue_tail = _slice_from_marker(
            _read(phases_dir, "dialogue.md"), _entry_marker(dialogue_next), "dialogue.md"
        )

        design_next, _ = PHASE_EXIT_OWNERS["design-team.md"]
        design_tail = _slice_from_marker(
            _read(phases_dir, "design-team.md"), _entry_marker(design_next), "design-team.md"
        )

        spec_next, _ = PHASE_EXIT_OWNERS["spec-review.md"]
        spec_tail = _slice_from_marker(
            _read(phases_dir, "spec-review.md"), _entry_marker(spec_next), "spec-review.md"
        )

        assert "that routing wins" in dialogue_tail, "dialogue.md: missing routing guard"
        assert "that routing wins" in design_tail, "design-team.md: missing routing guard"
        assert "only on the approval branch" in dialogue_tail, (
            "dialogue.md: missing approval-branch guard"
        )
        assert "stay in this phase" in design_tail, "design-team.md: missing stay-in-phase guard"
        assert "stay in this phase" in spec_tail, "spec-review.md: missing stay-in-phase guard"
        assert "proposal" not in spec_tail, "spec-review.md: 'proposal' leaked into entry-step tail"
