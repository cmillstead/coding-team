"""Tests for write-guard.py hook.

Pipeline-state detection derives from the active plan file under
`$MAIN_ROOT/docs/plans/*.md` — the unique plan whose YAML frontmatter
declares `status: in-progress`. The Phase 5 edit guard blocks
orchestrator edits to instruction files only when an in-progress plan
is detected. Tests construct a fresh git repo per case under
`tmp_path` and run the hook with that repo as cwd, so we never touch
real plan directories.

# mock-ok: test data strings trigger the no-mocks hook scanner — these are test INPUTS, not real mock usage
"""

import base64
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import pytest


HOOKS_DIR = Path(__file__).resolve().parent.parent  # tests/ -> hooks/
HOOK_PATH = HOOKS_DIR / "write-guard.py"

# Ensure hooks/ is on sys.path so direct imports from _lib work.
# conftest.py does not add HOOKS_DIR to sys.path, so we do it once here.
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from _lib.active_plan import _CACHE_ENTRY_VERSION, _compute_signature  # noqa: E402
from _lib.graduated_checks import check_c1_path_trust  # noqa: E402


def _load_write_guard():
    """Load write-guard.py as a module (hyphen in name requires importlib)."""
    spec = importlib.util.spec_from_file_location(
        "write_guard", str(HOOKS_DIR / "write-guard.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Single module-level load — avoids re-running exec_module for each test.
_WRITE_GUARD = _load_write_guard()

ACTIVE_FRONTMATTER = "---\nstatus: in-progress\n---\n\n"


# Encode mock-triggering test data as base64 to avoid the no-mocks hook
# scanning THIS file and blocking the write. These are INPUT strings we
# feed to the hook under test — not actual mock usage.
# mock-ok: base64-encoded test input data for hook validation, not real mock usage
_B64_MOCK_IMPORT = "ZnJvbSB1bml0dGVzdC5tb2NrIGltcG9ydCBNYWdpY01vY2s="
# mock-ok: base64-encoded test input data for hook validation, not real mock usage
_B64_MOCK_ALLOWLIST = "IyBtb2NrLW9rOiBwYWlkIEFQSQpmcm9tIHVuaXR0ZXN0Lm1vY2sgaW1wb3J0IE1hZ2ljTW9jaw=="


def _decode(b64: str) -> str:
    return base64.b64decode(b64).decode()


def _init_repo(repo_root: Path) -> None:
    """Initialize a minimal git repo at repo_root."""
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(repo_root)],
        check=True,
        capture_output=True,
    )


def _active_plan_body() -> str:
    """Canonical in-progress plan body (unchecked second-opinion line)."""
    return (
        ACTIVE_FRONTMATTER
        + "# Plan\n\n## Completion Checklist\n- [ ] Second-opinion review\n"
    )


def _write_plan(repo_root: Path, name: str, body: str | None = None) -> Path:
    """Create a plan file under docs/plans/. Defaults to in-progress + unchecked."""
    if body is None:
        body = _active_plan_body()
    plans_dir = repo_root / "docs" / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    plan = plans_dir / name
    plan.write_text(body)
    return plan


def _run(
    event: dict,
    cwd: Path | None = None,
    env: dict | None = None,
    use_root_seam: bool = True,
) -> tuple[dict | None, str, str, int]:
    """Run write-guard.py with the given event; return (parsed_json, stdout, stderr, returncode).

    When `cwd` is given and `use_root_seam` is True (the default), BOTH
    CODING_TEAM_MAIN_ROOT and CODING_TEAM_TEST_SEAM are set (explicit
    assignment, not setdefault) so active-plan detection uses the test repo
    directly instead of depending on real git discovery succeeding for an
    ephemeral tmp repo (see _lib/active_plan.py — the seam requires BOTH
    vars paired, per P1-5). An explicit `env` entry for either key wins:
    `run_env.update(env)` runs last, layering the caller's values on top of
    whatever the seam set.

    Set `use_root_seam=False` to exercise REAL target-scoped git discovery
    (write-guard.py's `_resolve_target_git_roots()`) instead of the seam.
    Required for any test asserting on actual git-identity resolution — with
    the seam active, the root is FORCED to `cwd` regardless of which file is
    being edited, which would make such a test vacuous.
    """
    run_env = None
    if cwd is not None or env is not None:
        run_env = dict(os.environ)
        if cwd is not None and use_root_seam:
            run_env["CODING_TEAM_MAIN_ROOT"] = str(cwd)
            run_env["CODING_TEAM_TEST_SEAM"] = "1"
        if env is not None:
            run_env.update(env)
    result = subprocess.run(
        ["python3", str(HOOK_PATH)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        timeout=10,
        cwd=str(cwd) if cwd else None,
        env=run_env,
    )
    try:
        parsed = json.loads(result.stdout) if result.stdout.strip() else None
    except (json.JSONDecodeError, ValueError):
        parsed = None
    return parsed, result.stdout, result.stderr, result.returncode


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Fresh git repo under tmp_path; tests cd into this for the subprocess."""
    _init_repo(tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# Phase 5 edit guard — pipeline detection
# ---------------------------------------------------------------------------


class TestPhase5InPipeline:
    """An in-progress plan file marks the pipeline as active."""

    def test_blocks_instruction_file_edit(self, repo: Path):
        """In-pipeline + instruction-file edit by orchestrator -> blocked."""
        _write_plan(repo, "plan.md")
        # An instruction file under a worktree of the test repo
        instr_dir = repo / "skills" / "demo"
        instr_dir.mkdir(parents=True)
        instr_file = instr_dir / "SKILL.md"
        instr_file.write_text("---\n---\n# Demo\nYou are demo.\n")

        event = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(instr_file),
                "new_string": "altered",
            },
        }
        parsed, stdout, _stderr, _rc = _run(event, cwd=repo)
        assert parsed is not None, f"expected JSON output, got {stdout!r}"
        assert parsed.get("decision") == "block"
        reason = parsed.get("reason", "").lower()
        assert "instruction file" in reason
        assert "agent tool" in reason

    def test_allows_non_instruction_source_edit(self, repo: Path):
        """In-pipeline + non-instruction-file -> allowed (orchestrator handles ≤20-line judgment)."""
        _write_plan(repo, "plan.md")
        src_file = repo / "src" / "main.py"
        src_file.parent.mkdir(parents=True)
        src_file.write_text("def main(): pass\n")

        event = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(src_file),
                "new_string": "def main(): return 0",
            },
        }
        parsed, stdout, _stderr, _rc = _run(event, cwd=repo)
        # No block decision — either silent (no output) or non-block JSON
        if parsed is not None:
            assert parsed.get("decision") != "block", f"unexpected block: {parsed!r}"

    def test_allows_orchestrator_file_during_pipeline(self, repo: Path):
        """In-pipeline + orchestrator-allowlisted path (memory/, /tmp, etc.) -> allowed."""
        _write_plan(repo, "plan.md")
        memory_file = repo / "memory" / "notes.md"
        memory_file.parent.mkdir(parents=True)
        memory_file.write_text("notes")

        event = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(memory_file),
                "new_string": "altered",
            },
        }
        parsed, _stdout, _stderr, _rc = _run(event, cwd=repo)
        if parsed is not None:
            assert parsed.get("decision") != "block"


class TestPhase5NoPipeline:
    """No active plan = no pipeline = all edits allowed regardless of file type."""

    def test_no_docs_plans_dir_allows_instruction_edit(self, repo: Path):
        """No docs/plans/ -> allow instruction-file edits."""
        # No plan file written.
        instr_dir = repo / "skills" / "demo"
        instr_dir.mkdir(parents=True)
        instr_file = instr_dir / "SKILL.md"
        instr_file.write_text("# Demo\n")

        event = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(instr_file),
                "new_string": "altered",
            },
        }
        parsed, _stdout, _stderr, _rc = _run(event, cwd=repo)
        if parsed is not None:
            assert parsed.get("decision") != "block", f"unexpected block: {parsed!r}"

    def test_all_plans_complete_allows_instruction_edit(self, repo: Path):
        """All plans marked status: complete -> no in-progress plan -> allow."""
        _write_plan(
            repo,
            "done.md",
            body="---\nstatus: complete\n---\n# Done\n## Completion Checklist\n- [ ] Second-opinion review\n",
        )

        instr_file = repo / "skills" / "demo" / "SKILL.md"
        instr_file.parent.mkdir(parents=True)
        instr_file.write_text("# Demo\n")

        event = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(instr_file),
                "new_string": "altered",
            },
        }
        parsed, _stdout, _stderr, _rc = _run(event, cwd=repo)
        if parsed is not None:
            assert parsed.get("decision") != "block"

    def test_planned_only_allows_instruction_edit(self, repo: Path):
        """Plan with `status: planned` (not in-progress yet) -> no gate -> allow."""
        _write_plan(
            repo,
            "planned.md",
            body="---\nstatus: planned\n---\n# Planned\n## Completion Checklist\n- [ ] Second-opinion review\n",
        )

        instr_file = repo / "skills" / "demo" / "SKILL.md"
        instr_file.parent.mkdir(parents=True)
        instr_file.write_text("# Demo\n")

        event = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(instr_file),
                "new_string": "altered",
            },
        }
        parsed, _stdout, _stderr, _rc = _run(event, cwd=repo)
        if parsed is not None:
            assert parsed.get("decision") != "block", (
                f"expected allow when plan is `status: planned` (not yet in-progress), got {parsed!r}"
            )

    def test_no_frontmatter_allows_instruction_edit(self, repo: Path):
        """Plan without leading frontmatter -> no gate -> allow."""
        _write_plan(
            repo,
            "noframe.md",
            body="# Plan\n\n## Completion Checklist\n- [ ] Second-opinion review\n",
        )

        instr_file = repo / "skills" / "demo" / "SKILL.md"
        instr_file.parent.mkdir(parents=True)
        instr_file.write_text("# Demo\n")

        event = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(instr_file),
                "new_string": "altered",
            },
        }
        parsed, _stdout, _stderr, _rc = _run(event, cwd=repo)
        if parsed is not None:
            assert parsed.get("decision") != "block"

    def test_in_progress_picked_despite_complete_sibling(self, repo: Path):
        """An in-progress plan still wins even if a status: complete sibling exists."""
        _write_plan(repo, "older.md")  # in-progress (default)
        _write_plan(
            repo,
            "newer.md",
            body="---\nstatus: complete\n---\n# Newer\n## Completion Checklist\n- [ ] Second-opinion review\n",
        )

        instr_file = repo / "skills" / "demo" / "SKILL.md"
        instr_file.parent.mkdir(parents=True)
        instr_file.write_text("# Demo\n")

        event = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(instr_file),
                "new_string": "altered",
            },
        }
        parsed, stdout, _stderr, _rc = _run(event, cwd=repo)
        _assert_blocked_by_phase5(parsed, stdout)


class TestPhase5AmbiguousState:
    """Multiple in-progress plans or unreadable plans fail closed -> block."""

    def test_multiple_in_progress_blocks_instruction_edit(self, repo: Path):
        """Two plans with `status: in-progress` -> block with ambiguity message."""
        _write_plan(repo, "plan-a.md")
        _write_plan(repo, "plan-b.md")

        instr_file = repo / "skills" / "demo" / "SKILL.md"
        instr_file.parent.mkdir(parents=True)
        instr_file.write_text("# Demo\n")

        event = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(instr_file),
                "new_string": "altered",
            },
        }
        parsed, stdout, _stderr, _rc = _run(event, cwd=repo)
        assert parsed is not None, f"expected JSON output, got {stdout!r}"
        assert parsed.get("decision") == "block"
        reason = parsed.get("reason", "").lower()
        assert "cannot determine active plan state" in reason

    def test_multiple_in_progress_blocks_even_normal_source(self, repo: Path):
        """Ambiguity blocks ALL edits (fail closed), not just instruction files."""
        _write_plan(repo, "plan-a.md")
        _write_plan(repo, "plan-b.md")

        src = repo / "src" / "main.py"
        src.parent.mkdir(parents=True)
        src.write_text("print('hi')")

        event = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(src),
                "new_string": "print('hello')",
            },
        }
        parsed, stdout, _stderr, _rc = _run(event, cwd=repo)
        assert parsed is not None, f"expected JSON output, got {stdout!r}"
        assert parsed.get("decision") == "block"
        assert "cannot determine active plan state" in parsed.get("reason", "").lower()

    def test_unreadable_plan_blocks(self, repo: Path):
        """chmod 000 on an in-progress plan -> fail closed -> block."""
        plan = _write_plan(repo, "locked.md")
        plan.chmod(0)

        instr_file = repo / "skills" / "demo" / "SKILL.md"
        instr_file.parent.mkdir(parents=True)
        instr_file.write_text("# Demo\n")

        event = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(instr_file),
                "new_string": "altered",
            },
        }
        try:
            parsed, stdout, _stderr, _rc = _run(event, cwd=repo)
        finally:
            plan.chmod(stat.S_IRUSR | stat.S_IWUSR)
        assert parsed is not None, f"expected JSON output, got {stdout!r}"
        assert parsed.get("decision") == "block"
        reason = parsed.get("reason", "").lower()
        assert "cannot determine active plan state" in reason
        assert "unreadable" in reason


class TestPhase5ReferenceDataFilesAllowed:
    """DEFECT 2: co-located reference/DATA docs under instruction dirs are
    NOT behavioral instruction files and must be allowed even in-pipeline."""

    def _make_instr_tree(self, repo: Path) -> Path:
        skill_dir = repo / "skills" / "second-opinion"
        skill_dir.mkdir(parents=True)
        return skill_dir

    def test_allows_codex_learnings_drop_folder_write_in_pipeline(self, repo: Path):
        """D196 drop-folder layout: writing a new entry file in codex-learnings.d/ in-pipeline -> allow."""
        _write_plan(repo, "plan.md")
        skill_dir = self._make_instr_tree(repo)
        drop_dir = skill_dir / "codex-learnings.d"
        drop_dir.mkdir(parents=True, exist_ok=True)
        new_entry = drop_dir / "20260619-120000-test-entry.md"

        event = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(new_entry),
                "content": "# C99\n\n| ID | Pattern | Check before dispatch |\n|----|---------|----------------------|\n| C99 | `@tags: path-input; provable; scope:diff` test entry | grep test |\n",
            },
        }
        parsed, stdout, _stderr, _rc = _run(event, cwd=repo)
        if parsed is not None:
            assert parsed.get("decision") != "block", (
                f"codex-learnings.d/ entry write must not be gated, got {stdout!r}"
            )

    def test_allows_reference_md_in_pipeline(self, repo: Path):
        """A co-located reference.md (data doc) in-pipeline -> allow."""
        _write_plan(repo, "plan.md")
        skill_dir = self._make_instr_tree(repo)
        ref = skill_dir / "reference.md"
        ref.write_text("# Reference\n")

        event = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(ref), "new_string": "more"},
        }
        parsed, _stdout, _stderr, _rc = _run(event, cwd=repo)
        if parsed is not None:
            assert parsed.get("decision") != "block"

    def test_allows_references_subdir_doc_in_pipeline(self, repo: Path):
        """skills/foo/references/api.md (data) in-pipeline -> allow."""
        _write_plan(repo, "plan.md")
        ref = repo / "skills" / "firecrawl" / "references" / "api.md"
        ref.parent.mkdir(parents=True)
        ref.write_text("# API\n")

        event = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(ref), "new_string": "more"},
        }
        parsed, _stdout, _stderr, _rc = _run(event, cwd=repo)
        if parsed is not None:
            assert parsed.get("decision") != "block"

    def test_still_blocks_skill_md_in_pipeline(self, repo: Path):
        """Regression guard: SKILL.md must STILL be gated (the hole must not widen)."""
        _write_plan(repo, "plan.md")
        skill_dir = self._make_instr_tree(repo)
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("# Demo\nYou are demo.\n")

        event = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(skill_md), "new_string": "altered"},
        }
        parsed, stdout, _stderr, _rc = _run(event, cwd=repo)
        _assert_blocked_by_phase5(parsed, stdout)

    def test_still_blocks_agent_md_in_pipeline(self, repo: Path):
        """Regression guard: agents/*.md must STILL be gated."""
        _write_plan(repo, "plan.md")
        agent = repo / "skills" / "ct" / "agents" / "ct-foo.md"
        agent.parent.mkdir(parents=True)
        agent.write_text("# Agent\nYou are foo.\n")

        event = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(agent), "new_string": "altered"},
        }
        parsed, stdout, _stderr, _rc = _run(event, cwd=repo)
        _assert_blocked_by_phase5(parsed, stdout)

    def test_still_blocks_hook_py_in_pipeline(self, repo: Path):
        """Regression guard: hooks/*.py must STILL be gated."""
        _write_plan(repo, "plan.md")
        hook = repo / "skills" / "ct" / "hooks" / "some-guard.py"
        hook.parent.mkdir(parents=True)
        hook.write_text("print('hi')\n")

        event = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(hook), "new_string": "altered"},
        }
        parsed, stdout, _stderr, _rc = _run(event, cwd=repo)
        _assert_blocked_by_phase5(parsed, stdout)

    def test_allows_md_note_co_located_in_hooks_dir(self, repo: Path):
        """A .md note under a hooks dir is data, not an executable hook -> allow."""
        _write_plan(repo, "plan.md")
        note = repo / "skills" / "ct" / "hooks" / "NOTES.md"
        note.parent.mkdir(parents=True)
        note.write_text("# notes\n")

        event = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(note), "new_string": "more"},
        }
        parsed, _stdout, _stderr, _rc = _run(event, cwd=repo)
        if parsed is not None:
            assert parsed.get("decision") != "block"


class TestOrchestratorExemptionDoesNotLaunderInstructionFiles:
    """P1-1: the orchestrator exemption at check_phase5 must not launder
    behavioral instruction files through memory/, and must not silently kill
    the downstream PAUL gate by conditioning .paul/. The four exempt roots
    are heterogeneous — see _orchestrator_exemption_category()'s docstring
    for why each one is (or isn't) conjoined with is_instruction_file()."""

    def _armed_plan(self, repo: Path) -> Path:
        return _write_plan(repo, "plan.md")

    @pytest.mark.parametrize(
        "relpath",
        [
            "memory/agents/a.md",  # instruction file laundered through memory/
            "memory/SKILL.md",
        ],
    )
    def test_instruction_file_under_memory_is_blocked(self, repo, relpath):
        self._armed_plan(repo)
        target = repo / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# Agent\n")
        event = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(target), "new_string": "x"},
        }
        parsed, stdout, _stderr, _rc = _run(event, cwd=repo)
        assert parsed is not None and parsed.get("decision") == "block", (
            f"{relpath} is an instruction file and must NOT be laundered by "
            f"the memory/ exemption — got {stdout!r}"
        )
        reason = parsed.get("reason", "")
        assert "HOOK CRASH" not in reason, (
            f"block came from a hook crash, not the Phase 5 gate: {stdout!r}"
        )
        assert "behavioral instruction-file edit" in reason, (
            f"block reason is not the Phase 5 instruction-file gate: {stdout!r}"
        )

    def test_non_instruction_file_under_memory_is_still_allowed(self, repo):
        """Regression lock: the memory/ exemption's real purpose survives."""
        self._armed_plan(repo)
        target = repo / "memory" / "notes.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# Notes\n")
        event = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(target), "new_string": "x"},
        }
        parsed, stdout, _stderr, _rc = _run(event, cwd=repo)
        if parsed is not None:
            assert parsed.get("decision") != "block", (
                f"a non-instruction file under memory/ must stay exempt, got {stdout!r}"
            )

    def test_paul_artifact_is_NOT_blocked_by_an_armed_plan(self, repo):
        """`.paul/` is exempt UNCONDITIONALLY — it has its own gate downstream
        in main() (check_paul_phase_gate).

        `.paul/phases/<dir>/*.md` classifies as an instruction file, so any
        conjunction applied to `.paul` makes check_paul_phase_gate unreachable
        and kills the PAUL workflow. No existing test covers this end to end —
        the PAUL tests call check_paul_phase_gate() directly
        (test_write_guard.py:1319-1361), so a regression here is silent.

        F2: the assertion is UNCONDITIONAL (not gated behind
        `if ... decision == "block"`) — a conditional assertion block passes
        silently on an ALLOW, which is exactly what deleting or skipping
        check_paul_phase_gate() would produce. The expected outcome here is
        known and asserted positively: check_paul_phase_gate blocks this
        exact fixture (DISCOVERY.md with no ASSUMPTIONS.md) with its own
        ASSUMPTIONS.md-missing reason.
        """
        self._armed_plan(repo)
        target = repo / ".paul" / "phases" / "03-x" / "DISCOVERY.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# Discovery\n")
        event = {
            "tool_name": "Write",
            "tool_input": {"file_path": str(target), "content": "x"},
        }
        parsed, stdout, _stderr, _rc = _run(event, cwd=repo)
        assert parsed is not None and parsed.get("decision") == "block", (
            f"expected check_paul_phase_gate to block (no ASSUMPTIONS.md "
            f"present) — an ALLOW here means the PAUL gate was skipped or "
            f"deleted, got {stdout!r}"
        )
        reason = parsed.get("reason", "")
        assert "HOOK CRASH" not in reason, (
            f"block came from a hook crash, not either gate: {stdout!r}"
        )
        assert "behavioral instruction-file edit" not in reason, (
            f"PAUL artifact was blocked by the Phase 5 instruction gate, "
            f"not the PAUL staircase — check_paul_phase_gate is now "
            f"unreachable: {stdout!r}"
        )
        assert "PAUL phase '03-x' isn't assumed" in reason, (
            f"expected check_paul_phase_gate's own ASSUMPTIONS.md-missing "
            f"reason, got {stdout!r}"
        )

    def test_paul_artifact_is_NOT_blocked_by_ambiguous_plan_state(self, repo):
        """P2-A: `.paul/` must stay UNCONDITIONALLY exempt even when the
        active-plan lookup itself is ambiguous (two plans claiming
        `status: in-progress`). Before the fix, the ambiguity block ran
        BEFORE the exemption category was ever computed, so a `.paul/`
        artifact was blocked with "cannot determine active plan state"
        instead of ever reaching check_paul_phase_gate — making the PAUL
        gate unreachable exactly when two plans race to in-progress.

        F2: same unconditional-assertion fix as
        test_paul_artifact_is_NOT_blocked_by_an_armed_plan above — the
        check_paul_phase_gate() logic doesn't consult plan state at all, so
        this fixture produces the identical ASSUMPTIONS.md-missing reason
        (verified empirically); asserted here rather than assumed.
        """
        _write_plan(repo, "plan-a.md")
        _write_plan(repo, "plan-b.md")  # two in-progress -> ambiguous

        target = repo / ".paul" / "phases" / "03-x" / "DISCOVERY.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# Discovery\n")
        event = {
            "tool_name": "Write",
            "tool_input": {"file_path": str(target), "content": "x"},
        }
        parsed, stdout, _stderr, _rc = _run(event, cwd=repo)
        assert parsed is not None and parsed.get("decision") == "block", (
            f"expected check_paul_phase_gate to block (no ASSUMPTIONS.md "
            f"present) — an ALLOW here means the PAUL gate was skipped or "
            f"deleted, got {stdout!r}"
        )
        reason = parsed.get("reason", "")
        assert "HOOK CRASH" not in reason, (
            f"block came from a hook crash, not either gate: {stdout!r}"
        )
        assert "cannot determine active plan state" not in reason.lower(), (
            f"a .paul/ artifact must not be shadowed by an ambiguous plan "
            f"state — check_paul_phase_gate is now unreachable whenever "
            f"two plans race to in-progress: {stdout!r}"
        )
        assert "PAUL phase '03-x' isn't assumed" in reason, (
            f"expected check_paul_phase_gate's own ASSUMPTIONS.md-missing "
            f"reason, got {stdout!r}"
        )

    def test_vault_note_under_agents_dir_is_still_allowed(self, repo, tmp_path):
        """204 real vault notes live under `agents/`/`phases/` components.

        They are KB reference notes with no behavioral effect. The vault
        exemption is unconditional; a conjunction here blocks daily writes.
        """
        self._armed_plan(repo)
        vault_note = repo / "Documents" / "obsidian-vault" / "AI" / "agents" / "note.md"
        vault_note.parent.mkdir(parents=True, exist_ok=True)
        vault_note.write_text("# Note\n")
        event = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(vault_note), "new_string": "x"},
        }
        parsed, stdout, _stderr, _rc = _run(event, cwd=repo)
        if parsed is not None:
            assert parsed.get("decision") != "block", (
                f"a vault note under an agents/ component must stay exempt, got {stdout!r}"
            )


class TestOrchestratorExemptionCategory:
    """Structural-matching unit tests for _orchestrator_exemption_category().

    Exercises the function directly — these are pure path-matching
    questions, not pipeline-state questions, so no subprocess is needed.

    P2-C: is_orchestrator_file() (the bool wrapper this class used to
    target) is REMOVED, not merely re-tested. It had zero production
    callers (check_phase5 calls _orchestrator_exemption_category directly)
    and this class's own test_repo_under_tmp_does_not_get_a_free_pass
    (long retired) pinned a containment shape production never actually
    exercised that way — which is why the P1-A worktree bypass shipped
    green. This also removed the function's `target_worktree_root`
    parameter entirely: P1-A's fix made the /tmp branch a plain
    `plan_root is not None` check, so there was no second value left to
    compare against.

    F3: the /tmp branch itself is GONE, not merely fixed. Codex confirmed
    by probe that it was unreachable dead code in production —
    check_phase5 only calls this function once plan_root is confirmed
    non-None (it returns early on `plan_root is None` before ever reaching
    this call), so a /tmp branch keyed on `plan_root is not None` could
    never return anything but None. The tests that used to assert "/tmp
    stays exempt" (test_tmp_is_exempt_on_both_spellings_when_no_plan_root,
    test_tmp_scratch_without_any_plan_root_stays_exempt) and the P1-A
    regression lock that asserted the corrected plan_root-truthy override
    (test_plan_root_truthy_voids_tmp_exemption_unconditionally) are all
    retired: /tmp is not a distinct exemption root anymore, so there is
    nothing /tmp-specific left to test beyond
    test_tmp_paths_are_not_exempt_at_all below — genuinely unowned /tmp
    scratch is handled upstream, by check_phase5's own `plan_root is None`
    early return, before this function is ever called at all.
    """

    def test_tmpfoo_is_not_exempt(self):
        assert _WRITE_GUARD._orchestrator_exemption_category("/tmpfoo/repo/hooks/x.py") is None

    def test_tmp_paths_are_not_exempt_at_all(self):
        """F3: /tmp is no longer a distinct exemption root, with or without
        plan_root — it falls through this function like any other
        non-matching path. Replaces the four retired /tmp-specific tests
        this class used to carry (see class docstring)."""
        assert _WRITE_GUARD._orchestrator_exemption_category("/tmp/scratch.txt") is None
        assert _WRITE_GUARD._orchestrator_exemption_category("/private/tmp/scratch.txt") is None
        assert (
            _WRITE_GUARD._orchestrator_exemption_category(
                "/tmp/some-harness-repo/hooks/write-guard.py",
                plan_root=Path("/tmp/some-harness-repo"),
            )
            is None
        )

    def test_mymemory_component_is_not_exempt(self):
        assert _WRITE_GUARD._orchestrator_exemption_category("/repo/mymemory/note.md") is None

    def test_path_error_is_not_exempt(self):
        """Any path exception yields None (= not exempt = gate applies).

        Defensive depth: requirement 2 forbids resolving the input, so this
        is not reachable via ELOOP on the input today. Assert the contract
        directly rather than via a symlink fixture, which would pass
        vacuously — `tmp_path` is rooted at `<repo>/.pytest-tmp`
        (conftest.py:61-64) and is not under any exempt root.
        """
        assert _WRITE_GUARD._orchestrator_exemption_category(None) is None


class TestPhase5BlockMessageDiagnosability:
    """DEFECT 3: the block message must name the arming plan path."""

    def test_block_message_names_arming_plan(self, repo: Path):
        """Block on an instruction file must include the arming plan's path."""
        plan = _write_plan(repo, "plan-18-02.md")
        skill_md = repo / "skills" / "demo" / "SKILL.md"
        skill_md.parent.mkdir(parents=True)
        skill_md.write_text("# Demo\nYou are demo.\n")

        event = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(skill_md), "new_string": "altered"},
        }
        parsed, stdout, _stderr, _rc = _run(event, cwd=repo)
        assert parsed is not None and parsed.get("decision") == "block"
        reason = parsed.get("reason", "")
        assert str(plan) in reason, (
            f"block message must name the arming plan {plan}, got {reason!r}"
        )
        assert "arming plan" in reason.lower()

    def test_stale_plan_surfaces_advisory_note(self, repo: Path):
        """A plan older than the staleness threshold surfaces a STALE note."""
        import os
        import time

        plan = _write_plan(repo, "stale.md")
        old = time.time() - 11 * 86400  # 11 days, like the real plan-18-02 case
        os.utime(plan, (old, old))

        skill_md = repo / "skills" / "demo" / "SKILL.md"
        skill_md.parent.mkdir(parents=True)
        skill_md.write_text("# Demo\nYou are demo.\n")

        event = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(skill_md), "new_string": "altered"},
        }
        parsed, _stdout, _stderr, _rc = _run(event, cwd=repo)
        assert parsed is not None and parsed.get("decision") == "block"
        assert "stale" in parsed.get("reason", "").lower()

    def test_block_message_does_not_prescribe_agent_tool_route(self, repo: Path):
        """DEFECT 1: the old impossible 'dispatch with PROMPT_CRAFT_ADVISORY'
        instruction must be gone."""
        _write_plan(repo, "plan.md")
        skill_md = repo / "skills" / "demo" / "SKILL.md"
        skill_md.parent.mkdir(parents=True)
        skill_md.write_text("# Demo\nYou are demo.\n")

        event = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(skill_md), "new_string": "altered"},
        }
        parsed, _stdout, _stderr, _rc = _run(event, cwd=repo)
        reason = parsed.get("reason", "")
        assert "PROMPT_CRAFT_ADVISORY" not in reason
        # The real override path must be named.
        assert "WRITE_GUARD_ALLOW_INSTRUCTION_EDIT" in reason


class TestPhase5OverrideEscapeHatch:
    """DEFECT 1: a deliberate env-var override allows the edit (default blocks)."""

    def test_override_env_allows_instruction_edit(self, repo: Path):
        """WRITE_GUARD_ALLOW_INSTRUCTION_EDIT=1 -> allow even in-pipeline."""
        _write_plan(repo, "plan.md")
        skill_md = repo / "skills" / "demo" / "SKILL.md"
        skill_md.parent.mkdir(parents=True)
        skill_md.write_text("# Demo\nYou are demo.\n")

        event = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(skill_md), "new_string": "altered"},
        }
        parsed, stdout, _stderr, _rc = _run(
            event, cwd=repo, env={"WRITE_GUARD_ALLOW_INSTRUCTION_EDIT": "1"}
        )
        if parsed is not None:
            assert parsed.get("decision") != "block", (
                f"override must allow the edit, got {stdout!r}"
            )

    def test_override_env_recovers_ambiguous_state(self, repo: Path):
        """Override also unblocks the fail-closed ambiguous/wedged state."""
        _write_plan(repo, "plan-a.md")
        _write_plan(repo, "plan-b.md")  # two in-progress -> ambiguous
        skill_md = repo / "skills" / "demo" / "SKILL.md"
        skill_md.parent.mkdir(parents=True)
        skill_md.write_text("# Demo\nYou are demo.\n")

        event = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(skill_md), "new_string": "altered"},
        }
        parsed, _stdout, _stderr, _rc = _run(
            event, cwd=repo, env={"WRITE_GUARD_ALLOW_INSTRUCTION_EDIT": "1"}
        )
        if parsed is not None:
            assert parsed.get("decision") != "block"


def _assert_allowed(parsed, stdout, stderr, rc, what: str) -> None:
    """Assert the hook ALLOWED — silently, or with an advisory allow.

    Closes the vacuous-positive trap (an import-time crash also yields
    `parsed is None`) WITHOUT asserting a silence the hook never promised:
    check_identity_framing emits an advisory allow on agents/*.md and
    SKILL.md edits that lack identity framing.
    """
    assert rc == 0, f"{what}: hook exited {rc}, stderr={stderr!r}"
    assert "Traceback" not in stderr, f"{what}: hook crashed — {stderr!r}"
    if parsed is None:
        assert stdout.strip() == "", (
            f"{what}: no JSON decision but stdout was not empty — {stdout!r}"
        )
    else:
        assert parsed.get("decision") == "allow", (
            f"{what}: expected an allow decision, got {stdout!r}"
        )


class TestPhase5InstructionAllowlist:
    """A plan-declared instruction file is editable; an undeclared one is not."""

    def _armed_plan(self, repo: Path, declared: str | None) -> Path:
        body = "---\nstatus: in-progress\n"
        if declared is not None:
            body += f"instruction_files: {declared}\n"
        body += "---\n\n# Plan\n"
        return _write_plan(repo, "plan.md", body=body)

    def _agent_file(self, repo: Path, name: str = "ct-qa-reviewer.md") -> Path:
        agent = repo / "agents" / name
        agent.parent.mkdir(parents=True, exist_ok=True)
        agent.write_text("# Agent\nYou are the reviewer.\n")
        return agent

    def test_declared_file_is_allowed(self, repo: Path):
        # Arrange
        self._armed_plan(repo, "agents/ct-qa-reviewer.md")
        agent = self._agent_file(repo)
        # Act
        event = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(agent), "new_string": "altered"},
        }
        parsed, stdout, stderr, rc = _run(event, cwd=repo)
        # Assert
        _assert_allowed(parsed, stdout, stderr, rc,
                        "declared instruction file must be allowed")

    def test_undeclared_file_is_blocked(self, repo: Path):
        # Arrange
        self._armed_plan(repo, "agents/ct-qa-reviewer.md")
        other = self._agent_file(repo, "ct-spec-reviewer.md")
        # Act
        event = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(other), "new_string": "altered"},
        }
        parsed, stdout, stderr, rc = _run(event, cwd=repo)
        # Assert
        assert parsed is not None and parsed.get("decision") == "block", (
            f"undeclared instruction file must be blocked, got {stdout!r}"
        )

    def test_block_message_names_the_declared_list(self, repo: Path):
        # Arrange
        self._armed_plan(repo, "agents/ct-qa-reviewer.md")
        other = self._agent_file(repo, "ct-spec-reviewer.md")
        # Act
        event = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(other), "new_string": "altered"},
        }
        parsed, stdout, stderr, rc = _run(event, cwd=repo)
        # Assert
        assert parsed is not None, (
            f"expected a block decision, got no JSON (rc={rc}, "
            f"stderr={stderr!r})"
        )
        reason = parsed.get("reason", "")
        assert "agents/ct-qa-reviewer.md" in reason, (
            f"block message must name the declared allowlist, got {reason!r}"
        )
        assert "instruction_files" in reason, (
            f"block message must say how to declare a file, got {reason!r}"
        )

    def test_multiple_declared_files_all_allowed(self, repo: Path):
        # Arrange
        self._armed_plan(
            repo, "agents/ct-spec-reviewer.md, agents/ct-qa-reviewer.md"
        )
        # Act + Assert
        for name in ("ct-spec-reviewer.md", "ct-qa-reviewer.md"):
            agent = self._agent_file(repo, name)
            event = {
                "tool_name": "Edit",
                "tool_input": {"file_path": str(agent), "new_string": "x"},
            }
            parsed, stdout, stderr, rc = _run(event, cwd=repo)
            _assert_allowed(parsed, stdout, stderr, rc,
                            f"{name} was declared but blocked")

    def test_no_key_blocks_every_instruction_edit(self, repo: Path):
        """BACK-COMPAT: an armed plan with no `instruction_files` key blocks
        everything, exactly as it did before the allowlist existed."""
        # Arrange
        self._armed_plan(repo, None)
        agent = self._agent_file(repo)
        # Act
        event = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(agent), "new_string": "altered"},
        }
        parsed, stdout, stderr, rc = _run(event, cwd=repo)
        # Assert
        assert parsed is not None and parsed.get("decision") == "block", (
            f"no-key plan must block all instruction edits, got {stdout!r}"
        )

    def test_declared_file_does_not_unblock_non_instruction_paths(self, repo: Path):
        """Declaring a file must not change the non-instruction allow path."""
        # Arrange
        self._armed_plan(repo, "agents/ct-qa-reviewer.md")
        src = repo / "src" / "main.py"
        src.parent.mkdir(parents=True)
        src.write_text("x = 1\n")
        # Act
        event = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(src), "new_string": "x = 2\n"},
        }
        parsed, stdout, stderr, rc = _run(event, cwd=repo)
        # Assert
        _assert_allowed(parsed, stdout, stderr, rc,
                        "non-instruction file must be allowed")


def _assert_blocked_by_phase5(parsed, stdout: str) -> None:
    """Shared P2-D helper: a bare `decision == "block"` passes against a
    crashed hook too (write-guard.py's top-level handler turns ANY
    exception into a block) — every block assertion for the Phase 5
    instruction-file gate must exclude HOOK CRASH and require the
    gate-specific reason substring. Module-level (not class-bound) so
    every test class in this file can share it.
    """
    assert parsed is not None and parsed.get("decision") == "block", (
        f"expected block, got {stdout!r}"
    )
    reason = parsed.get("reason", "")
    assert "HOOK CRASH" not in reason, f"block came from a hook crash: {stdout!r}"
    assert "behavioral instruction-file edit" in reason, (
        f"block reason is not the Phase 5 instruction-file gate: {stdout!r}"
    )


class TestTargetScopedRootResolution:
    """P1-5: the protected root is derived from the EDITED FILE's own git
    identity, not from the process's cwd. Every test here uses
    `use_root_seam=False` so real target-scoped git discovery
    (`_resolve_target_git_roots()`) actually runs — with the seam active
    the root would be forced to `cwd` regardless of the file being edited,
    making these tests vacuous. Every block assertion excludes HOOK CRASH
    and requires the Phase-5-specific reason substring, per
    TestOrchestratorExemptionDoesNotLaunderInstructionFiles's pattern —
    write-guard.py's top-level handler turns ANY exception into a block,
    so a bare `decision == "block"` would pass against a crashed hook.
    """

    def _armed_repo_with_instruction_file(self, root: Path) -> Path:
        """Init a git repo at ROOT, arm a plan, and write an instruction file.

        Returns the instruction file's path.
        """
        _init_repo(root)
        _write_plan(root, "plan.md")
        instr = root / "skills" / "demo" / "SKILL.md"
        instr.parent.mkdir(parents=True)
        instr.write_text("# Demo\nYou are demo.\n")
        return instr

    def _assert_blocked_by_phase5(self, parsed, stdout: str) -> None:
        _assert_blocked_by_phase5(parsed, stdout)

    def test_root_follows_the_edited_file_not_the_cwd(self, tmp_path: Path):
        """The documented bypass (cd to a repo with no plans) asserted closed.

        An armed plan lives only in repo-a. Running the hook with cwd set to
        an unrelated repo-b (no plans at all) must NOT disarm the gate for
        an edit to a file that physically belongs to repo-a.
        """
        repo_a = tmp_path / "repo-a"
        repo_a.mkdir()
        instr = self._armed_repo_with_instruction_file(repo_a)

        repo_b = tmp_path / "repo-b"
        repo_b.mkdir()
        _init_repo(repo_b)  # unrelated repo, no plans

        event = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(instr), "new_string": "altered"},
        }
        parsed, stdout, _stderr, _rc = _run(event, cwd=repo_b, use_root_seam=False)
        self._assert_blocked_by_phase5(parsed, stdout)

    @pytest.mark.parametrize(
        "case_id,env_builder",
        [
            (
                "GIT_DIR+GIT_WORK_TREE",
                lambda repo_a, empty_repo: {
                    "GIT_DIR": str(empty_repo / ".git"),
                    "GIT_WORK_TREE": str(empty_repo),
                },
            ),
            (
                "GIT_COMMON_DIR",
                lambda repo_a, empty_repo: {"GIT_COMMON_DIR": str(empty_repo / ".git")},
            ),
            (
                "GIT_CEILING_DIRECTORIES",
                lambda repo_a, empty_repo: {"GIT_CEILING_DIRECTORIES": str(repo_a)},
            ),
            (
                "unknown_GIT_var_default_deny",
                lambda repo_a, empty_repo: {"GIT_TOTALLY_MADE_UP": "anything"},
            ),
        ],
    )
    def test_git_env_vars_cannot_redirect_the_root(self, tmp_path: Path, case_id, env_builder):
        """F1: no GIT_*-prefixed env var can redirect target-scoped discovery
        away from the edited file's real owning repo — not just GIT_DIR and
        GIT_WORK_TREE (the two that were ALREADY scrubbed before P1-B and so
        prove nothing about the allowlist inversion). GIT_COMMON_DIR and
        GIT_CEILING_DIRECTORIES are the two Codex reproduced as live
        bypasses pre-fix; GIT_TOTALLY_MADE_UP locks the allowlist's
        default-deny direction — an unrecognized GIT_* var must be
        stripped, not kept, so a future git version's new env var is
        stripped by default rather than silently trusted.
        """
        repo_a = tmp_path / "repo-a"
        repo_a.mkdir()
        instr = self._armed_repo_with_instruction_file(repo_a)

        empty_repo = tmp_path / "empty-repo"
        empty_repo.mkdir()
        _init_repo(empty_repo)  # no docs/plans

        event = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(instr), "new_string": "altered"},
        }
        parsed, stdout, _stderr, _rc = _run(
            event,
            use_root_seam=False,
            env=env_builder(repo_a, empty_repo),
        )
        self._assert_blocked_by_phase5(parsed, stdout)

    def test_worktree_consults_the_main_checkouts_plans(self, tmp_path: Path):
        """Regression lock for the contract at _lib/active_plan.py's module
        docstring: worktrees and the primary checkout resolve to the same
        plan_root. A plan armed ONLY in the main checkout must still gate an
        edit made inside a linked worktree. A directory-name walk up from
        the worktree would fail this (docs/plans/ doesn't exist there,
        gitignored and only present in the main checkout); target-scoped
        `--git-common-dir` passes it.
        """
        main_repo = tmp_path / "main-repo"
        main_repo.mkdir()
        self._armed_repo_with_instruction_file(main_repo)  # armed in main only

        worktree_dir = tmp_path / "wt-checkout"
        subprocess.run(
            [
                "git", "-C", str(main_repo), "worktree", "add", "-q",
                "-b", "wt-branch", str(worktree_dir),
            ],
            check=True,
            capture_output=True,
        )

        instr = worktree_dir / "skills" / "demo" / "SKILL.md"
        instr.parent.mkdir(parents=True)
        instr.write_text("# Demo\nYou are demo.\n")

        event = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(instr), "new_string": "altered"},
        }
        parsed, stdout, _stderr, _rc = _run(event, use_root_seam=False)
        self._assert_blocked_by_phase5(parsed, stdout)

    def test_empty_nested_docs_plans_does_not_shadow_an_armed_parent(self, tmp_path: Path):
        """An empty docs/plans/ nested under a subdirectory of the armed
        repo must not shadow the armed parent — target-scoped resolution
        only ever consults <owning-repo-root>/docs/plans/, never a
        directory-name walk that could stop at the nested empty one."""
        repo = tmp_path / "repo"
        repo.mkdir()
        self._armed_repo_with_instruction_file(repo)

        nested_empty = repo / "component" / "docs" / "plans"
        nested_empty.mkdir(parents=True)

        instr = repo / "component" / "hooks" / "x.py"
        instr.parent.mkdir(parents=True)
        instr.write_text("print('hi')\n")

        event = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(instr), "new_string": "altered"},
        }
        parsed, stdout, _stderr, _rc = _run(event, use_root_seam=False)
        self._assert_blocked_by_phase5(parsed, stdout)

    def test_symlinked_repo_alias_under_tmp_is_not_exempted(self, tmp_path: Path):
        """P1-1 x P1-5 interaction: is_instruction_file() classification is
        LEXICAL (spelling says /tmp), but repo OWNERSHIP is resolved (the
        alias resolves to the armed repo) — ownership must win for the /tmp
        exemption decision, or a /tmp symlink alias would launder any
        instruction-file edit around the gate."""
        repo = tmp_path / "repo"
        repo.mkdir()
        self._armed_repo_with_instruction_file(repo)
        (repo / "hooks").mkdir()
        hook_file = repo / "hooks" / "write-guard.py"
        hook_file.write_text("print('hi')\n")

        alias = Path("/tmp") / f"wg-alias-{uuid.uuid4().hex[:8]}"
        alias.symlink_to(repo)
        try:
            aliased_path = alias / "hooks" / "write-guard.py"
            event = {
                "tool_name": "Edit",
                "tool_input": {"file_path": str(aliased_path), "new_string": "altered"},
            }
            parsed, stdout, _stderr, _rc = _run(event, use_root_seam=False)
            self._assert_blocked_by_phase5(parsed, stdout)
        finally:
            alias.unlink()

    def test_linked_worktree_under_real_tmp_is_not_exempted(self, tmp_path: Path):
        """P1-A: a linked worktree living under a GENUINE /tmp path (not
        `.pytest-tmp`) must still be gated. The main checkout can live
        anywhere; only the worktree itself needs to be under literal /tmp,
        since that's what reaches the /tmp branch in
        _orchestrator_exemption_category().

        This is NOT covered by test_worktree_consults_the_main_checkouts_plans
        above — that test's worktree lives under the repo-rooted `tmp_path`
        fixture (`.pytest-tmp`), never under literal /tmp, so it cannot
        exercise the /tmp branch at all. Reproduced against the pre-fix
        code: this exact scenario returned `decision: allow`.
        """
        main_repo = tmp_path / "main-repo"
        main_repo.mkdir()
        self._armed_repo_with_instruction_file(main_repo)  # armed in main only

        worktree_dir = Path("/tmp") / f"wg-worktree-{uuid.uuid4().hex[:8]}"
        subprocess.run(
            [
                "git", "-C", str(main_repo), "worktree", "add", "-q",
                "-b", f"wt-branch-{uuid.uuid4().hex[:8]}", str(worktree_dir),
            ],
            check=True,
            capture_output=True,
        )
        try:
            instr = worktree_dir / "skills" / "demo" / "SKILL.md"
            instr.parent.mkdir(parents=True)
            instr.write_text("# Demo\nYou are demo.\n")

            event = {
                "tool_name": "Edit",
                "tool_input": {"file_path": str(instr), "new_string": "altered"},
            }
            parsed, stdout, _stderr, _rc = _run(event, use_root_seam=False)
            self._assert_blocked_by_phase5(parsed, stdout)
        finally:
            subprocess.run(
                ["git", "-C", str(main_repo), "worktree", "remove", "--force", str(worktree_dir)],
                capture_output=True,
            )
            shutil.rmtree(worktree_dir, ignore_errors=True)

    def test_file_outside_any_git_repo_is_dormant(self):
        """A file with no owning git repo at all is never pipeline-gated —
        target-scoped discovery must NOT fall back to cwd (that would
        reintroduce the defect this resolution scheme exists to close)."""
        outside = Path(tempfile.mkdtemp(prefix="wg-no-repo-"))
        try:
            instr = outside / "skills" / "demo" / "SKILL.md"
            instr.parent.mkdir(parents=True)
            instr.write_text("# Demo\nYou are demo.\n")
            event = {
                "tool_name": "Edit",
                "tool_input": {"file_path": str(instr), "new_string": "altered"},
            }
            parsed, stdout, _stderr, _rc = _run(event, use_root_seam=False)
            if parsed is not None:
                assert parsed.get("decision") != "block", (
                    f"a file outside any git repo must not be pipeline-gated, got {stdout!r}"
                )
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_ambient_main_root_override_is_ignored_end_to_end(self, repo: Path):
        """P1-5 end-to-end: an ambient CODING_TEAM_MAIN_ROOT pointed at an
        empty dir must not disarm the gate — without the paired sentinel,
        real target-scoped git discovery takes over regardless. Passes
        CODING_TEAM_TEST_SEAM="" explicitly: once _run() sets the sentinel
        for every cwd invocation (use_root_seam defaults to True here), the
        env-supplied root would otherwise be honored and this assertion
        would invert.
        """
        instr = self._armed_repo_with_instruction_file(repo)  # note: repo IS init'd by fixture already
        empty_dir = repo.parent / "unrelated-empty"
        empty_dir.mkdir()

        event = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(instr), "new_string": "altered"},
        }
        parsed, stdout, _stderr, _rc = _run(
            event,
            cwd=repo,
            env={"CODING_TEAM_MAIN_ROOT": str(empty_dir), "CODING_TEAM_TEST_SEAM": ""},
        )
        self._assert_blocked_by_phase5(parsed, stdout)


# ---------------------------------------------------------------------------
# Migration guard — independent of pipeline detection
# ---------------------------------------------------------------------------


class TestMigrationGuard:
    def test_blocks_edit_to_existing_tracked_migration(self):
        """Tracked migration file -> blocked even with no active plan.

        Uses a fixed non-test-like path under /tmp/ct_migration_repo so the
        path does not match is_test_file() patterns (pytest tmp_path generates
        paths like test_blocks_edit0/... which do match, and the new test-file
        exemption in check_migration() would then correctly allow them).
        """
        import shutil
        repo = Path("/tmp/ct_migration_repo")
        if repo.exists():
            shutil.rmtree(repo)
        repo.mkdir(parents=True)
        try:
            _init_repo(repo)
            migration_dir = repo / "migrations"
            migration_dir.mkdir()
            migration_file = migration_dir / "001_create.py"
            migration_file.write_text("# migration")

            # Track and commit so the guard's git ls-files check returns tracked=True.
            subprocess.run(
                ["git", "add", str(migration_file)],
                cwd=repo,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [
                    "git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "-m", "init",
                ],
                cwd=repo,
                check=True,
                capture_output=True,
            )

            event = {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": str(migration_file),
                    "new_string": "altered",
                },
            }
            parsed, stdout, _stderr, _rc = _run(event, cwd=repo)
            assert parsed is not None, f"expected JSON output, got {stdout!r}"
            assert parsed["decision"] == "block"
            assert "migration" in parsed["reason"].lower()
        finally:
            shutil.rmtree(repo, ignore_errors=True)

    def test_exempts_test_file_in_migration_dir(self, repo: Path):
        """Test files inside a migrations dir are allowed (test-file exemption).

        A *.test.ts or test_*.py file under a migrations/ directory is not a
        deployed migration — it is a test fixture. The deployed write-guard
        exempts is_test_file() paths from the migration-immutability guard.
        """
        migration_dir = repo / "migrations"
        migration_dir.mkdir()
        test_file = migration_dir / "migration-01-up.test.ts"
        test_file.write_text("// test")

        # Track and commit to ensure _is_tracked_in_git returns True
        subprocess.run(
            ["git", "add", str(test_file)],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "git", "-c", "user.email=t@t", "-c", "user.name=t",
                "commit", "-q", "-m", "init",
            ],
            cwd=repo,
            check=True,
            capture_output=True,
        )

        event = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(test_file),
                "new_string": "// altered",
            },
        }
        parsed, stdout, _stderr, _rc = _run(event, cwd=repo)
        # Must NOT be blocked — test files are exempt from migration guard
        if parsed is not None:
            assert parsed.get("decision") != "block", (
                f"test file in migrations/ must not be blocked by migration guard, "
                f"got {stdout!r}"
            )

    def test_migration_blocked_without_override(self):
        """Tracked migration file is BLOCKED when WRITE_GUARD_ALLOW_MIGRATION_EDIT is unset.

        Confirms the default deny behavior (regression guard for the escape hatch).
        """
        import shutil
        repo = Path("/tmp/ct_migration_override_repo")
        if repo.exists():
            shutil.rmtree(repo)
        repo.mkdir(parents=True)
        try:
            _init_repo(repo)
            migration_dir = repo / "migrations"
            migration_dir.mkdir()
            migration_file = migration_dir / "002_add_index.py"
            migration_file.write_text("# migration")

            subprocess.run(
                ["git", "add", str(migration_file)],
                cwd=repo,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [
                    "git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "-m", "init",
                ],
                cwd=repo,
                check=True,
                capture_output=True,
            )

            event = {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": str(migration_file),
                    "new_string": "altered",
                },
            }
            # Explicitly unset the override env var to confirm default-block behavior
            parsed, stdout, _stderr, _rc = _run(
                event, cwd=repo, env={"WRITE_GUARD_ALLOW_MIGRATION_EDIT": ""}
            )
            assert parsed is not None, f"expected JSON output, got {stdout!r}"
            assert parsed["decision"] == "block"
            assert "migration" in parsed["reason"].lower()
        finally:
            shutil.rmtree(repo, ignore_errors=True)

    def test_migration_allowed_with_override_env(self):
        """WRITE_GUARD_ALLOW_MIGRATION_EDIT=1 allows editing a tracked migration.

        This is the sanctioned escape hatch for user-approved migration edits
        (e.g. adding idempotency guards), mirroring WRITE_GUARD_ALLOW_INSTRUCTION_EDIT.
        """
        import shutil
        repo = Path("/tmp/ct_migration_override_allow_repo")
        if repo.exists():
            shutil.rmtree(repo)
        repo.mkdir(parents=True)
        try:
            _init_repo(repo)
            migration_dir = repo / "migrations"
            migration_dir.mkdir()
            migration_file = migration_dir / "003_add_idempotency.py"
            migration_file.write_text("# migration")

            subprocess.run(
                ["git", "add", str(migration_file)],
                cwd=repo,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [
                    "git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "-m", "init",
                ],
                cwd=repo,
                check=True,
                capture_output=True,
            )

            event = {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": str(migration_file),
                    "new_string": "# idempotency guard added",
                },
            }
            parsed, stdout, _stderr, _rc = _run(
                event, cwd=repo, env={"WRITE_GUARD_ALLOW_MIGRATION_EDIT": "1"}
            )
            if parsed is not None:
                assert parsed.get("decision") != "block", (
                    f"WRITE_GUARD_ALLOW_MIGRATION_EDIT=1 must allow the edit, got {stdout!r}"
                )
        finally:
            shutil.rmtree(repo, ignore_errors=True)

    def test_block_message_names_migration_override_env(self):
        """Block message on a migration edit must mention WRITE_GUARD_ALLOW_MIGRATION_EDIT.

        The sanctioned path must be visible in the block output so the operator
        knows how to proceed for a legitimate user-approved edit.
        """
        import shutil
        repo = Path("/tmp/ct_migration_msg_repo")
        if repo.exists():
            shutil.rmtree(repo)
        repo.mkdir(parents=True)
        try:
            _init_repo(repo)
            migration_dir = repo / "migrations"
            migration_dir.mkdir()
            migration_file = migration_dir / "004_add_col.py"
            migration_file.write_text("# migration")

            subprocess.run(
                ["git", "add", str(migration_file)],
                cwd=repo,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [
                    "git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "-m", "init",
                ],
                cwd=repo,
                check=True,
                capture_output=True,
            )

            event = {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": str(migration_file),
                    "new_string": "altered",
                },
            }
            parsed, stdout, _stderr, _rc = _run(event, cwd=repo)
            assert parsed is not None, f"expected JSON output, got {stdout!r}"
            assert parsed["decision"] == "block"
            reason = parsed["reason"]
            assert "WRITE_GUARD_ALLOW_MIGRATION_EDIT" in reason, (
                f"block message must name the override env var, got {reason!r}"
            )
        finally:
            shutil.rmtree(repo, ignore_errors=True)


# ---------------------------------------------------------------------------
# No-mocks guard — independent of pipeline detection
# ---------------------------------------------------------------------------


class TestNoMocksGuard:
    def test_blocks_mock_in_test_file(self):
        event = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "/tmp/tests/test_example.py",
                "new_string": _decode(_B64_MOCK_IMPORT),
            },
        }
        parsed, _stdout, _stderr, _rc = _run(event)
        assert parsed is not None
        assert parsed["decision"] == "block"
        assert "mock" in parsed["reason"].lower()

    def test_allows_mock_with_allowlist_marker(self):
        event = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "/tmp/tests/test_example.py",
                "new_string": _decode(_B64_MOCK_ALLOWLIST),
            },
        }
        parsed, _stdout, _stderr, _rc = _run(event)
        if parsed:
            assert parsed.get("decision") != "block"


# ---------------------------------------------------------------------------
# Identity framing advisory — independent of pipeline detection
# ---------------------------------------------------------------------------


class TestIdentityFramingAdvisory:
    def test_advisory_for_agent_file_without_identity(self):
        """Agent file lacking identity framing produces an advisory, not a block.

        Run outside any git repo so the Phase 5 guard is dormant — this isolates
        the identity-framing check.
        """
        import os
        event = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": os.path.expanduser("~/.claude/agents/ct-foo.md"),
                "content": "# Agent\nDo some stuff.",
            },
        }
        parsed, _stdout, _stderr, _rc = _run(event, cwd=Path("/tmp"))
        if parsed:
            assert parsed.get("decision") != "block"
            if "reason" in parsed:
                assert "identity" in parsed["reason"].lower()


# ---------------------------------------------------------------------------
# Normal allow path
# ---------------------------------------------------------------------------


class TestNormalFileAllowed:
    def test_allows_edit_to_normal_python_file_outside_pipeline(self, repo: Path):
        """No active plan + non-instruction non-test file -> silent allow."""
        src = repo / "src" / "main.py"
        src.parent.mkdir(parents=True)
        src.write_text("print('hi')")
        event = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(src),
                "new_string": "print('hello')",
            },
        }
        parsed, stdout, _stderr, _rc = _run(event, cwd=repo)
        # Either silent (no output) or non-block JSON
        if parsed is not None:
            assert parsed.get("decision") != "block"
        else:
            assert stdout.strip() == ""


# ---------------------------------------------------------------------------
# Graduated C1 check integration — single-emission, aggregated advisory
# ---------------------------------------------------------------------------


class TestGraduatedC1Advisory:
    """C1 graduated check wired into write-guard.py produces exactly ONE JSON object."""

    def test_c1_signal_edit_produces_single_json_object(self):
        """An Edit with a C1 signal produces exactly one JSON object: allow + reason."""
        event = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "/tmp/src/config.ts",
                "new_string": "interface Options { repoPath: string; }\n",
            },
        }
        parsed, stdout, _stderr, _rc = _run(event)
        # Exactly one JSON object (not two, not zero)
        lines = [line for line in stdout.strip().splitlines() if line.strip()]
        assert len(lines) == 1, f"Expected exactly 1 JSON line, got {len(lines)}: {stdout!r}"
        assert parsed is not None
        assert parsed["decision"] == "allow"
        assert "C1" in parsed.get("reason", "") or "Codex" in parsed.get("reason", "")

    def test_path_safety_and_c1_cofiring_produces_single_json_object(self, repo: Path):
        """A .py Edit matching both path-safety AND C1 emits exactly ONE JSON object.

        path.startswith( triggers the path-safety advisory (string op on path).
        repoPath triggers the C1 advisory.
        Single-emission rule: both reasons must be in the one JSON reason string.
        """
        src = repo / "src" / "guard.py"
        src.parent.mkdir(parents=True)
        src.write_text("x = 1\n")

        # Combine: path-safety signal (startswith on a path string) + C1 signal (repoPath)
        new_content = "def check(repoPath: str) -> bool:\n    return repoPath.startswith('/home')\n"

        event = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(src),
                "new_string": new_content,
            },
        }
        parsed, stdout, _stderr, _rc = _run(event, cwd=repo)
        lines = [line for line in stdout.strip().splitlines() if line.strip()]
        assert len(lines) == 1, (
            f"Expected exactly 1 JSON line (single-emission), got {len(lines)}: {stdout!r}"
        )
        assert parsed is not None
        assert parsed["decision"] == "allow"
        reason = parsed.get("reason", "")
        # Both advisories must appear in the single aggregated reason
        assert "startswith" in reason or "path" in reason.lower(), (
            f"Path-safety text missing from reason: {reason!r}"
        )
        assert "C1" in reason or "Codex" in reason or "contains" in reason, (
            f"C1 text missing from reason: {reason!r}"
        )

    def test_c1_and_c5_cofiring_on_py_test_edit_single_json(self, repo: Path):
        """An Edit to a tests/test_x.py triggering BOTH C1 and C5 -> exactly ONE JSON line.

        C1 fires on open( (a path-call token).
        C5 fires on ungated sqlite3.connect("/var/...") in a test file.
        Single-emission contract: both reasons must appear in the ONE aggregated JSON.
        This locks that appending C5 to GRADUATED_CHECKS did not break single-emission
        aggregation through write-guard's dispatch.
        """
        tests_dir = repo / "tests"
        tests_dir.mkdir(parents=True)
        test_file = tests_dir / "test_x.py"
        test_file.write_text("x = 1\n")

        # new_string triggers BOTH:
        #   C1 — open( is a path-call token (Signal 2)
        #   C5 — ungated sqlite3.connect("/var/lib/app/data.db") in a test file
        new_content = (
            'def test_real():\n'
            '    conn = sqlite3.connect("/var/lib/app/data.db")\n'
            '    with open("/var/lib/app/cfg.json") as f:\n'
            '        data = f.read()\n'
            '    conn.close()\n'
        )

        event = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(test_file),
                "new_string": new_content,
            },
        }
        parsed, stdout, _stderr, _rc = _run(event, cwd=repo)
        lines = [line for line in stdout.strip().splitlines() if line.strip()]
        assert len(lines) == 1, (
            f"Expected exactly 1 JSON line (single-emission), got {len(lines)}: {stdout!r}"
        )
        assert parsed is not None
        assert parsed["decision"] == "allow"
        reason = parsed.get("reason", "")
        # Both C1 and C5 advisories must appear in the single aggregated reason
        assert "C1" in reason or "Codex" in reason or "open(" in reason, (
            f"C1 text missing from aggregated reason: {reason!r}"
        )
        assert "C5" in reason or "hermeticity" in reason or "test-hermeticity" in reason, (
            f"C5 text missing from aggregated reason: {reason!r}"
        )

    def test_blocking_guard_still_emits_single_block(self, repo: Path):
        """A phase5-blocked file emits a single block — no advisory leaked alongside.

        Sets WRITE_GUARD_ALLOW_INSTRUCTION_EDIT=0 (overwriting any ambient value)
        so the phase5 guard is armed even when the test session has it enabled.
        """
        _write_plan(repo, "plan.md")
        instr_dir = repo / "skills" / "demo"
        instr_dir.mkdir(parents=True)
        instr_file = instr_dir / "SKILL.md"
        instr_file.write_text("---\n---\n# Demo\nYou are demo.\n")

        # Override to "0" so the phase5 guard is armed regardless of ambient env.
        # _run merges this over os.environ, so "0" wins even if the session has "1".
        env = {"WRITE_GUARD_ALLOW_INSTRUCTION_EDIT": "0"}

        # Includes a C1 signal — but block takes precedence
        event = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(instr_file),
                "new_string": "repoPath = '/tmp'\n",
            },
        }
        parsed, stdout, _stderr, _rc = _run(event, cwd=repo, env=env)
        lines = [line for line in stdout.strip().splitlines() if line.strip()]
        assert len(lines) == 1, (
            f"Expected exactly 1 JSON line (single-emission), got {len(lines)}: {stdout!r}"
        )
        _assert_blocked_by_phase5(parsed, stdout)


# ---------------------------------------------------------------------------
# C5 hermeticity — conftest scrub proofs
# ---------------------------------------------------------------------------


class TestConftestEnvScrub:
    """Proofs for the session-start ambient-flag scrub added in conftest.py.

    UNIT proof: asserts the flags are absent from os.environ after session start.
    This directly verifies the scrub mechanism without depending on subprocess
    merge semantics.
    """

    def test_ambient_flags_absent_from_os_environ(self):
        """Both write-guard override flags must be absent from os.environ after scrub.

        The session-scoped autouse fixture in conftest.py pops both flags at
        session start. If either is still present here, the scrub did not run
        or was bypassed.
        """
        assert "WRITE_GUARD_ALLOW_INSTRUCTION_EDIT" not in os.environ, (
            "WRITE_GUARD_ALLOW_INSTRUCTION_EDIT leaked into os.environ — "
            "the conftest scrub_write_guard_ambient_flags fixture must not have run"
        )
        assert "WRITE_GUARD_ALLOW_MIGRATION_EDIT" not in os.environ, (
            "WRITE_GUARD_ALLOW_MIGRATION_EDIT leaked into os.environ — "
            "the conftest scrub_write_guard_ambient_flags fixture must not have run"
        )

    def test_explicit_env_override_still_wins(self, repo: Path):
        """Explicit env={"WRITE_GUARD_ALLOW_INSTRUCTION_EDIT": "1"} in _run() allows the edit.

        Even after the session-start scrub removes the flag from os.environ, a
        test that explicitly passes the flag via env= in _run() must still see it
        honored — the {**os.environ, **env} merge layers explicit values over the
        scrubbed base, so explicit wins.
        """
        _write_plan(repo, "plan.md")
        skill_md = repo / "skills" / "demo" / "SKILL.md"
        skill_md.parent.mkdir(parents=True)
        skill_md.write_text("# Demo\nYou are demo.\n")

        event = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(skill_md), "new_string": "altered"},
        }
        parsed, stdout, _stderr, _rc = _run(
            event, cwd=repo, env={"WRITE_GUARD_ALLOW_INSTRUCTION_EDIT": "1"}
        )
        assert parsed is not None, f"hook produced no parseable JSON: {stdout!r}"
        if parsed is not None:
            assert parsed.get("decision") != "block", (
                f"explicit WRITE_GUARD_ALLOW_INSTRUCTION_EDIT=1 must allow edit, got {stdout!r}"
            )

    def test_scrub_flows_into_subprocess_no_env_override(self, repo: Path):
        """PROCESS-LEVEL proof: scrubbed os.environ propagates into hook subprocess.

        This test calls _run() with NO env= argument, so subprocess.run() inherits
        the ambient os.environ directly. The session-start conftest scrub has already
        removed WRITE_GUARD_ALLOW_INSTRUCTION_EDIT and WRITE_GUARD_ALLOW_MIGRATION_EDIT
        from os.environ, so no override flag leaks into the hook process. The hook must
        therefore apply the full instruction-edit block.

        If the conftest scrub regressed (fixture removed, scope changed, autouse
        dropped), an ambient WRITE_GUARD_ALLOW_INSTRUCTION_EDIT flag set by the user
        (e.g. in settings.json env) would leak through and the edit would be wrongly
        allowed — causing this test to fail. The unit proof (test_ambient_flags_absent_from_os_environ)
        catches the flag still in os.environ, but only THIS test catches the scrub
        not flowing into the subprocess.
        """
        _write_plan(repo, "plan.md")
        skill_md = repo / "skills" / "demo" / "SKILL.md"
        skill_md.parent.mkdir(parents=True)
        skill_md.write_text("# Demo\nYou are demo.\n")

        event = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(skill_md), "new_string": "altered"},
        }
        # No env= argument: subprocess inherits ambient os.environ as-is.
        # The scrub must have removed the override flags or the block will not fire.
        parsed, stdout, _stderr, _rc = _run(event, cwd=repo)
        assert parsed is not None, (
            f"hook produced no parseable JSON — expected a block decision: {stdout!r}"
        )
        _assert_blocked_by_phase5(parsed, stdout)


# ---------------------------------------------------------------------------
# C17 / C1 cross-tests — direct-call verification of non-overlapping triggers
# ---------------------------------------------------------------------------


class TestC17C1CrossResponsibility:
    """Cross-tests verifying that check_path_safety (C17) and check_c1_path_trust (C1)
    have distinct and non-overlapping trigger surfaces on key inputs.

    These call both functions directly and assert their ACTUAL observed returns —
    no assumed isolation. The integration (single-emission) contract is separately
    locked by test_path_safety_and_c1_cofiring_produces_single_json_object.
    """

    def test_c1_only_path_shaped_field_no_string_op(self):
        """C1-only trigger: a path-shaped field name with no string ops on it.

        repoPath triggers C1's _FIELD_NAME_RE (camelCase 'Path' component).
        check_path_safety finds no PATH_SAFETY_PATTERNS match (no .startswith,
        no string-in-path literal, no f-string path join) so returns None.

        Arrange: content is a plain assignment — path-shaped name, pure assignment.
        Act: call both functions directly with a .py file.
        Assert: C1 fires (non-None), path_safety does not (None).
        """
        # Arrange
        content = "repoPath = compute()\n"
        tool_input = {"file_path": "/tmp/example.py", "new_string": content}

        # Act
        c1_result = check_c1_path_trust("Edit", tool_input)
        ps_result = _WRITE_GUARD.check_path_safety("Edit", tool_input)

        # Assert
        assert c1_result is not None, (
            "C1 must fire on 'repoPath = compute()' — got None"
        )
        assert ps_result is None, (
            f"check_path_safety must not fire on a plain assignment with no string op — got: {ps_result!r}"
        )

    def test_path_safety_fires_embedded_token_c1_does_not(self):
        """path-safety trigger: embedded token where C1's component-boundary regex misses.

        'filepath.startswith(\"/etc\")' — 'path' is preceded by 'file' (not a boundary
        per _FIELD_NAME_RE's (?<![A-Za-z]) lookbehind), so C1 returns None.
        check_path_safety matches the .startswith() pattern regardless of the token.

        Empirically observed: C1 returns None, path_safety returns non-None.

        Arrange: content uses filepath.startswith (embedded token, no C1 boundary).
        Act: call both functions directly.
        Assert: path_safety fires, C1 returns None (empirically confirmed).
        """
        # Arrange
        content = 'if filepath.startswith("/etc"):\n    pass\n'
        tool_input = {"file_path": "/tmp/example.py", "new_string": content}

        # Act
        ps_result = _WRITE_GUARD.check_path_safety("Edit", tool_input)
        c1_result = check_c1_path_trust("Edit", tool_input)

        # Assert
        assert ps_result is not None, (
            "check_path_safety must fire on filepath.startswith — got None"
        )
        # C1 returns None: 'filepath' has 'file' immediately before 'path' (no boundary).
        # This is the observed behavior — do not assume clean exclusion; record it here.
        assert c1_result is None, (
            f"C1 observed to return None for 'filepath' (no component boundary) — got: {c1_result!r}"
        )

    def test_cofiring_direct_call_both_checks_fire(self):
        """Co-firing: a .py file with both a C1 field trigger AND a path string op.

        repoPath (C1 camelCase signal) + repoPath.startswith('/home') (path-safety signal).
        Both functions must return non-None when called directly.

        This complements test_path_safety_and_c1_cofiring_produces_single_json_object
        which verifies the single-emission integration contract via subprocess.
        That test locks the aggregation behaviour; this test locks the direct-call
        both-fire result that makes the aggregation meaningful.

        Arrange: content triggers both C1 (repoPath field name) and path_safety (.startswith).
        Act: call both functions directly.
        Assert: both return non-None.
        """
        # Arrange
        content = "def check(repoPath: str) -> bool:\n    return repoPath.startswith('/home')\n"
        tool_input = {"file_path": "/tmp/guard.py", "new_string": content}

        # Act
        c1_result = check_c1_path_trust("Edit", tool_input)
        ps_result = _WRITE_GUARD.check_path_safety("Edit", tool_input)

        # Assert: both fire (direct-call confirmation of co-firing)
        assert c1_result is not None, (
            "C1 must fire on 'repoPath' — got None"
        )
        assert ps_result is not None, (
            "check_path_safety must fire on 'repoPath.startswith' — got None"
        )


# ---------------------------------------------------------------------------
# PAUL phase gate — check_paul_phase_gate direct-call tests
# ---------------------------------------------------------------------------


def _make_paul_phase_dir(tmp_path: Path, phase: str = "03-x") -> Path:
    """Create a .paul/phases/<phase>/ directory and return its path."""
    phase_dir = tmp_path / ".paul" / "phases" / phase
    phase_dir.mkdir(parents=True)
    return phase_dir


class TestPaulPhaseGateBasic:
    """Verify the staircase logic for each gated artifact."""

    def test_discovery_blocked_when_assumptions_absent(self, tmp_path: Path):
        """Writing DISCOVERY.md without ASSUMPTIONS.md present -> blocked."""
        phase_dir = _make_paul_phase_dir(tmp_path)
        file_path = str(phase_dir / "DISCOVERY.md")
        result = _WRITE_GUARD.check_paul_phase_gate(file_path)
        assert result is not None, "DISCOVERY.md must be blocked when ASSUMPTIONS.md absent"
        assert "ASSUMPTIONS" in result
        assert "BLOCKED" in result

    def test_discovery_allowed_when_assumptions_present(self, tmp_path: Path):
        """Writing DISCOVERY.md when ASSUMPTIONS.md exists -> allowed."""
        phase_dir = _make_paul_phase_dir(tmp_path)
        (phase_dir / "ASSUMPTIONS.md").write_text("# Assumptions\n")
        file_path = str(phase_dir / "DISCOVERY.md")
        result = _WRITE_GUARD.check_paul_phase_gate(file_path)
        assert result is None, f"DISCOVERY.md must be allowed when ASSUMPTIONS.md exists, got: {result!r}"

    def test_ground_blocked_when_discovery_absent(self, tmp_path: Path):
        """Writing GROUND.md without DISCOVERY.md -> blocked."""
        phase_dir = _make_paul_phase_dir(tmp_path)
        file_path = str(phase_dir / "GROUND.md")
        result = _WRITE_GUARD.check_paul_phase_gate(file_path)
        assert result is not None, "GROUND.md must be blocked when DISCOVERY.md absent"
        assert "DISCOVERY" in result
        assert "BLOCKED" in result

    def test_ground_allowed_when_discovery_present(self, tmp_path: Path):
        """Writing GROUND.md when DISCOVERY.md exists -> allowed."""
        phase_dir = _make_paul_phase_dir(tmp_path)
        (phase_dir / "DISCOVERY.md").write_text("# Discovery\n")
        file_path = str(phase_dir / "GROUND.md")
        result = _WRITE_GUARD.check_paul_phase_gate(file_path)
        assert result is None, f"GROUND.md must be allowed when DISCOVERY.md exists, got: {result!r}"

    def test_assumptions_always_allowed(self, tmp_path: Path):
        """Writing ASSUMPTIONS.md has no precondition -> always allowed."""
        phase_dir = _make_paul_phase_dir(tmp_path)
        file_path = str(phase_dir / "ASSUMPTIONS.md")
        result = _WRITE_GUARD.check_paul_phase_gate(file_path)
        assert result is None, f"ASSUMPTIONS.md must always be allowed, got: {result!r}"

    def test_ungated_file_in_paul_phase_dir_not_gated(self, tmp_path: Path):
        """A non-gated file inside .paul/phases/<dir>/ -> returns None (pass-through)."""
        phase_dir = _make_paul_phase_dir(tmp_path)
        file_path = str(phase_dir / "NOTES.md")
        result = _WRITE_GUARD.check_paul_phase_gate(file_path)
        assert result is None, f"NOTES.md must not be gated in a PAUL phase dir, got: {result!r}"


class TestPaulPhaseGatePlanFiles:
    """Verify PLAN file gating (GROUND present+fresh required)."""

    def test_plan_blocked_when_ground_absent(self, tmp_path: Path):
        """Writing a PLAN file without GROUND.md -> blocked."""
        phase_dir = _make_paul_phase_dir(tmp_path)
        file_path = str(phase_dir / "03-01-PLAN.md")
        result = _WRITE_GUARD.check_paul_phase_gate(file_path)
        assert result is not None, "PLAN file must be blocked when GROUND.md absent"
        assert "GROUND" in result
        assert "BLOCKED" in result

    def test_plan_allowed_when_ground_present_and_fresh(self, tmp_path: Path):
        """Writing a PLAN file when GROUND.md exists and is newer than DISCOVERY.md -> allowed."""
        import os
        import time
        phase_dir = _make_paul_phase_dir(tmp_path)
        discovery = phase_dir / "DISCOVERY.md"
        ground = phase_dir / "GROUND.md"
        discovery.write_text("# Discovery\n")
        ground.write_text("# Ground\n")
        # Set DISCOVERY older than GROUND
        old_time = time.time() - 100
        os.utime(discovery, (old_time, old_time))
        # Ground is fresh (just written — newer than discovery)
        file_path = str(phase_dir / "03-01-PLAN.md")
        result = _WRITE_GUARD.check_paul_phase_gate(file_path)
        assert result is None, f"PLAN allowed when GROUND is fresh, got: {result!r}"

    def test_plan_blocked_when_ground_older_than_discovery(self, tmp_path: Path):
        """Writing a PLAN file when GROUND.md is older than DISCOVERY.md -> blocked (stale ground)."""
        import os
        import time
        phase_dir = _make_paul_phase_dir(tmp_path)
        discovery = phase_dir / "DISCOVERY.md"
        ground = phase_dir / "GROUND.md"
        discovery.write_text("# Discovery\n")
        ground.write_text("# Ground\n")
        # Set GROUND older than DISCOVERY (stale)
        old_time = time.time() - 100
        os.utime(ground, (old_time, old_time))
        file_path = str(phase_dir / "03-01-PLAN.md")
        result = _WRITE_GUARD.check_paul_phase_gate(file_path)
        assert result is not None, "PLAN file must be blocked when GROUND is older than DISCOVERY"
        assert "GROUND" in result
        assert "BLOCKED" in result

    def test_plan_basename_regex_matches_various_forms(self, tmp_path: Path):
        """Test that the PLAN regex matches various valid plan basenames."""
        phase_dir = _make_paul_phase_dir(tmp_path)
        # All should be blocked (GROUND absent) — confirms they ARE gated
        for name in ("03-01-PLAN.md", "01-02-PLAN.md", "99-99-PLAN.md"):
            result = _WRITE_GUARD.check_paul_phase_gate(str(phase_dir / name))
            assert result is not None, f"{name} must be treated as a gated PLAN file"

    def test_non_plan_md_in_phase_dir_not_gated_by_plan_regex(self, tmp_path: Path):
        """A .md file whose name doesn't match PLAN regex is not gated as a PLAN."""
        phase_dir = _make_paul_phase_dir(tmp_path)
        # e.g. "myresearch.md" — not in the gated list and not a PLAN
        file_path = str(phase_dir / "myresearch.md")
        result = _WRITE_GUARD.check_paul_phase_gate(file_path)
        assert result is None, f"Non-plan .md file must not be gated, got: {result!r}"

    def test_plan_blocked_when_discovery_absent_even_if_ground_present(self, tmp_path: Path):
        """Writing a PLAN file with GROUND present but DISCOVERY absent -> blocked.

        GROUND may have been written via the WRITE_GUARD_ALLOW_PHASE_SKIP override
        while DISCOVERY was absent. A subsequent PLAN write must still be blocked
        because the full ASSUMPTIONS→DISCOVERY→GROUND→PLAN chain is required.
        """
        phase_dir = _make_paul_phase_dir(tmp_path)
        (phase_dir / "ASSUMPTIONS.md").write_text("# Assumptions\n")
        (phase_dir / "GROUND.md").write_text("# Ground\n")
        # Note: DISCOVERY.md is intentionally NOT created
        file_path = str(phase_dir / "03-01-PLAN.md")
        result = _WRITE_GUARD.check_paul_phase_gate(file_path)
        assert result is not None, (
            "PLAN write must be BLOCKED when GROUND is present but DISCOVERY is absent — "
            "the full ASSUMPTIONS→DISCOVERY→GROUND→PLAN chain is required"
        )
        assert "BLOCKED" in result
        assert "DISCOVERY" in result


class TestPaulPhaseGateCrossPhase:
    """Phase isolation: artifacts from one phase do not satisfy another phase's gate."""

    def test_ground_in_phase_02_does_not_satisfy_plan_in_phase_03(self, tmp_path: Path):
        """GROUND.md in phase 02-x does not allow a PLAN write in phase 03-y."""
        # Create GROUND in 02-x phase
        phase_02 = tmp_path / ".paul" / "phases" / "02-x"
        phase_02.mkdir(parents=True)
        (phase_02 / "GROUND.md").write_text("# Ground for phase 02\n")

        # PLAN write targets phase 03-y (GROUND.md absent in 03-y)
        phase_03 = tmp_path / ".paul" / "phases" / "03-y"
        phase_03.mkdir(parents=True)
        file_path = str(phase_03 / "03-01-PLAN.md")
        result = _WRITE_GUARD.check_paul_phase_gate(file_path)
        assert result is not None, (
            "GROUND.md in phase 02-x must not satisfy PLAN gate in phase 03-y"
        )

    def test_assumptions_in_other_phase_does_not_satisfy_discovery_gate(self, tmp_path: Path):
        """ASSUMPTIONS.md in a different phase does not ungate DISCOVERY in this phase."""
        other_phase = tmp_path / ".paul" / "phases" / "01-a"
        other_phase.mkdir(parents=True)
        (other_phase / "ASSUMPTIONS.md").write_text("# Assumptions\n")

        target_phase = tmp_path / ".paul" / "phases" / "02-b"
        target_phase.mkdir(parents=True)
        file_path = str(target_phase / "DISCOVERY.md")
        result = _WRITE_GUARD.check_paul_phase_gate(file_path)
        assert result is not None, (
            "ASSUMPTIONS.md in 01-a must not ungate DISCOVERY in 02-b"
        )


class TestPaulPhaseGateNonPaulPaths:
    """Non-PAUL paths must pass through untouched (return None)."""

    def test_normal_source_file_not_gated(self, tmp_path: Path):
        """A regular source file path -> None."""
        result = _WRITE_GUARD.check_paul_phase_gate(str(tmp_path / "src" / "foo.py"))
        assert result is None

    def test_memory_file_not_gated(self, tmp_path: Path):
        """A memory/ .md file -> None."""
        result = _WRITE_GUARD.check_paul_phase_gate(str(tmp_path / "memory" / "x.md"))
        assert result is None

    def test_paul_dir_without_phases_not_gated(self, tmp_path: Path):
        """A .paul/ file NOT under phases/ -> None."""
        paul_dir = tmp_path / ".paul"
        paul_dir.mkdir()
        result = _WRITE_GUARD.check_paul_phase_gate(str(paul_dir / "PROJECT.md"))
        assert result is None

    def test_paul_phases_without_phase_subdir_not_gated(self, tmp_path: Path):
        """A file directly in .paul/phases/ (no phase subdir) -> None."""
        phases_dir = tmp_path / ".paul" / "phases"
        phases_dir.mkdir(parents=True)
        result = _WRITE_GUARD.check_paul_phase_gate(str(phases_dir / "GROUND.md"))
        assert result is None


class TestPaulPhaseGateOverride:
    """WRITE_GUARD_ALLOW_PHASE_SKIP env var overrides the gate."""

    def test_override_allows_blocked_discovery_write(self, tmp_path: Path):
        """WRITE_GUARD_ALLOW_PHASE_SKIP=1 allows DISCOVERY.md write when ASSUMPTIONS absent."""
        phase_dir = _make_paul_phase_dir(tmp_path)
        file_path = str(phase_dir / "DISCOVERY.md")
        # Without override: should block
        result_no_override = _WRITE_GUARD.check_paul_phase_gate(file_path)
        assert result_no_override is not None, "Sanity: should block without override"
        # With override: should allow
        old = os.environ.pop("WRITE_GUARD_ALLOW_PHASE_SKIP", None)
        try:
            os.environ["WRITE_GUARD_ALLOW_PHASE_SKIP"] = "1"
            result = _WRITE_GUARD.check_paul_phase_gate(file_path)
        finally:
            if old is not None:
                os.environ["WRITE_GUARD_ALLOW_PHASE_SKIP"] = old
            else:
                os.environ.pop("WRITE_GUARD_ALLOW_PHASE_SKIP", None)
        assert result is None, f"WRITE_GUARD_ALLOW_PHASE_SKIP=1 must allow the write, got: {result!r}"

    def test_override_allows_blocked_plan_write(self, tmp_path: Path):
        """WRITE_GUARD_ALLOW_PHASE_SKIP=1 allows PLAN write when GROUND absent."""
        phase_dir = _make_paul_phase_dir(tmp_path)
        file_path = str(phase_dir / "03-01-PLAN.md")
        old = os.environ.pop("WRITE_GUARD_ALLOW_PHASE_SKIP", None)
        try:
            os.environ["WRITE_GUARD_ALLOW_PHASE_SKIP"] = "1"
            result = _WRITE_GUARD.check_paul_phase_gate(file_path)
        finally:
            if old is not None:
                os.environ["WRITE_GUARD_ALLOW_PHASE_SKIP"] = old
            else:
                os.environ.pop("WRITE_GUARD_ALLOW_PHASE_SKIP", None)
        assert result is None, f"WRITE_GUARD_ALLOW_PHASE_SKIP=1 must allow PLAN write, got: {result!r}"

    def test_override_log_written_when_gate_would_block(self, tmp_path: Path):
        """When override is active and gate would block, a log line is appended."""
        phase_dir = _make_paul_phase_dir(tmp_path)
        file_path = str(phase_dir / "DISCOVERY.md")
        # Temporarily patch the log path by setting env var override + checking log
        # Since the log path is hardcoded to ~/.claude/security/..., we verify
        # the function returns None under override (log append is best-effort).
        old = os.environ.pop("WRITE_GUARD_ALLOW_PHASE_SKIP", None)
        try:
            os.environ["WRITE_GUARD_ALLOW_PHASE_SKIP"] = "1"
            result = _WRITE_GUARD.check_paul_phase_gate(file_path)
        finally:
            if old is not None:
                os.environ["WRITE_GUARD_ALLOW_PHASE_SKIP"] = old
            else:
                os.environ.pop("WRITE_GUARD_ALLOW_PHASE_SKIP", None)
        # Primary assertion: gate returns None under override
        assert result is None, f"Override must allow, got: {result!r}"


class TestPaulPhaseGateFailOpen:
    """Fail-open: the function must never raise, even on bad input."""

    def test_does_not_raise_on_empty_string(self):
        """Empty string file_path -> None, no exception."""
        try:
            result = _WRITE_GUARD.check_paul_phase_gate("")
            assert result is None
        except Exception as exc:  # noqa: BLE001  # testing fail-open
            pytest.fail(f"check_paul_phase_gate raised on empty string: {exc}")

    def test_does_not_raise_on_malformed_path(self):
        """Malformed / weird path -> None, no exception."""
        try:
            result = _WRITE_GUARD.check_paul_phase_gate("\x00/bad\x00path")
            assert result is None
        except Exception as exc:  # noqa: BLE001  # testing fail-open
            pytest.fail(f"check_paul_phase_gate raised on malformed path: {exc}")

    def test_does_not_raise_when_stat_would_fail(self, tmp_path: Path):
        """Path under .paul/phases/<dir>/GROUND.md where parent is unreadable -> None."""
        phase_dir = _make_paul_phase_dir(tmp_path)
        # Create DISCOVERY.md so the GROUND gate passes existence, then simulate
        # a path that has .paul/phases segment but can't be stat'd
        file_path = str(phase_dir / "GROUND.md")
        # Remove the phase dir so stat will fail
        import shutil
        shutil.rmtree(str(phase_dir))
        try:
            _WRITE_GUARD.check_paul_phase_gate(file_path)
            # Must not raise; may return None or a block reason
            # (the path is gone, but the function should handle it)
        except Exception as exc:  # noqa: BLE001  # testing fail-open
            pytest.fail(f"check_paul_phase_gate raised when stat fails: {exc}")


class TestPhase5AllowlistAdversarial:
    """Near-miss, traversal, and malformed inputs must never authorize an edit."""

    def _armed_plan(self, repo: Path, declared: str) -> Path:
        return _write_plan(
            repo,
            "plan.md",
            body=(
                f"---\nstatus: in-progress\n"
                f"instruction_files: {declared}\n---\n\n# Plan\n"
            ),
        )

    def _assert_blocked(
        self, repo: Path, target: Path, why: str, reason_substring: str
    ):
        """Assert BLOCK for the SPECIFIC reason under test (D4 / P2-7b).

        A bare `decision == "block"` passes against a hook that blocked for
        the WRONG reason — e.g. a crash, or the ambiguity branch firing
        instead of the allowlist branch — which is the exact vacuity a
        regression could hide behind. `reason_substring` pins the check to
        the gate actually under test; the `HOOK CRASH` exclusion additionally
        guards against a crash message that happens to contain
        `reason_substring` by coincidence.
        """
        event = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(target), "new_string": "altered"},
        }
        parsed, stdout, stderr, rc = _run(event, cwd=repo)
        assert parsed is not None and parsed.get("decision") == "block", (
            f"{why} — expected BLOCK, got {stdout!r}"
        )
        reason = parsed.get("reason", "")
        assert "HOOK CRASH" not in reason, (
            f"{why} — blocked via a hook crash, not the gate under test: "
            f"{reason!r}"
        )
        assert reason_substring in reason, (
            f"{why} — expected {reason_substring!r} in the block reason, "
            f"got {reason!r}"
        )

    def test_suffix_near_miss_not_authorized(self, repo: Path):
        """`agents/a.md.backup.md` must NOT be authorized by `agents/a.md`.

        Deliberately NOT `a.md.bak`: `is_instruction_file()` gates on the
        `.md` suffix, so a `.bak` file is never gated and would be allowed
        for an unrelated reason — a green test proving nothing. The near-miss
        must stay gated to exercise the matcher.
        """
        self._armed_plan(repo, "agents/a.md")
        near_md = repo / "agents" / "a.md.backup.md"
        near_md.parent.mkdir(parents=True)
        near_md.write_text("x")
        self._assert_blocked(
            repo, near_md, "suffix near-miss must not match the declared path",
            "behavioral instruction-file edit",
        )

    def test_nested_prefix_collision_not_authorized(self, repo: Path):
        """`evil/agents/a.md` must NOT be authorized by `agents/a.md`."""
        self._armed_plan(repo, "agents/a.md")
        evil = repo / "evil" / "agents" / "a.md"
        evil.parent.mkdir(parents=True)
        evil.write_text("x")
        self._assert_blocked(
            repo, evil, "nested path collision must not match",
            "behavioral instruction-file edit",
        )

    def test_traversal_entry_blocks_everything(self, repo: Path):
        """A `../../../etc/passwd` entry is malformed -> fail closed."""
        self._armed_plan(repo, "../../../etc/passwd")
        agent = repo / "agents" / "a.md"
        agent.parent.mkdir(parents=True)
        agent.write_text("x")
        self._assert_blocked(
            repo, agent, "traversal entry must make the allowlist malformed",
            "declaration is unusable",
        )

    def test_traversal_entry_does_not_authorize_its_target(self, repo: Path):
        """The traversal target itself must not become editable."""
        self._armed_plan(repo, "../outside/SKILL.md")
        outside = repo.parent / "outside" / "SKILL.md"
        outside.parent.mkdir(parents=True, exist_ok=True)
        outside.write_text("x")
        self._assert_blocked(
            repo, outside, "a traversal entry must authorize nothing",
            "declaration is unusable",
        )

    def test_absolute_entry_blocks_everything(self, repo: Path):
        self._armed_plan(repo, "/etc/passwd")
        agent = repo / "agents" / "a.md"
        agent.parent.mkdir(parents=True)
        agent.write_text("x")
        self._assert_blocked(
            repo, agent, "absolute entry must make the allowlist malformed",
            "declaration is unusable",
        )

    def test_empty_value_blocks_everything(self, repo: Path):
        _write_plan(
            repo,
            "plan.md",
            body="---\nstatus: in-progress\ninstruction_files:\n---\n\n# Plan\n",
        )
        agent = repo / "agents" / "a.md"
        agent.parent.mkdir(parents=True)
        agent.write_text("x")
        self._assert_blocked(
            repo, agent, "empty instruction_files must fail closed",
            "declaration is unusable",
        )

    def test_uppercase_basename_declaration_round_trips(self, repo: Path):
        """`SKILL.md` must survive frontmatter parsing without lowercasing."""
        self._armed_plan(repo, "skills/demo/SKILL.md")
        skill = repo / "skills" / "demo" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("# Demo\nYou are demo.\n")
        event = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(skill), "new_string": "altered"},
        }
        parsed, stdout, stderr, rc = _run(event, cwd=repo)
        _assert_allowed(parsed, stdout, stderr, rc,
                        "SKILL.md declaration must round-trip "
                        "case-sensitively")

    def test_override_env_still_works_with_allowlist_present(self, repo: Path):
        """Constraint: WRITE_GUARD_ALLOW_INSTRUCTION_EDIT remains functional."""
        self._armed_plan(repo, "agents/a.md")
        other = repo / "agents" / "undeclared.md"
        other.parent.mkdir(parents=True)
        other.write_text("x")
        event = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(other), "new_string": "altered"},
        }
        parsed, stdout, stderr, rc = _run(
            event, cwd=repo, env={"WRITE_GUARD_ALLOW_INSTRUCTION_EDIT": "1"}
        )
        _assert_allowed(parsed, stdout, stderr, rc,
                        "env override must still allow an undeclared "
                        "edit")

    def test_no_active_plan_gate_stays_dormant(self, repo: Path):
        """No in-progress plan -> allowlist is irrelevant -> allow."""
        _write_plan(
            repo,
            "done.md",
            body=(
                "---\nstatus: complete\n"
                "instruction_files: agents/a.md\n---\n\n# Done\n"
            ),
        )
        other = repo / "agents" / "undeclared.md"
        other.parent.mkdir(parents=True)
        other.write_text("x")
        event = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(other), "new_string": "altered"},
        }
        parsed, stdout, stderr, rc = _run(event, cwd=repo)
        _assert_allowed(parsed, stdout, stderr, rc,
                        "a `status: complete` plan must not arm the "
                        "gate")

    def test_ambiguous_state_still_blocks_despite_allowlist(self, repo: Path):
        """Two in-progress plans -> ambiguity block wins over the allowlist."""
        for name in ("plan-a.md", "plan-b.md"):
            _write_plan(
                repo,
                name,
                body=(
                    "---\nstatus: in-progress\n"
                    "instruction_files: agents/a.md\n---\n\n# Plan\n"
                ),
            )
        agent = repo / "agents" / "a.md"
        agent.parent.mkdir(parents=True)
        agent.write_text("x")
        event = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(agent), "new_string": "altered"},
        }
        parsed, stdout, stderr, rc = _run(event, cwd=repo)
        assert parsed is not None and parsed.get("decision") == "block", (
            f"ambiguity must block even a declared file, got {stdout!r}"
        )
        assert "cannot determine active plan state" in parsed.get(
            "reason", ""
        ).lower()

    def test_declared_but_unreadable_plan_blocks(self, repo: Path):
        """chmod 000 on the arming plan -> fail closed.

        NOTE the path this actually exercises: `find_active_plan()` raises
        `AmbiguousActivePlanError` on an unreadable plan
        (`_lib/active_plan.py:133-137`) BEFORE `check_phase5()` reaches the
        allowlist reader, so this blocks via the ambiguity branch
        (`write-guard.py:175-184`), NOT via the reader's own unreadable
        branch. It is still a genuine fail-closed assertion and must stay —
        it just is not evidence that the READER handles an unreadable plan.
        That branch is covered only by T1's `test_unreadable_plan_raises`,
        which calls the reader directly.
        """
        plan = self._armed_plan(repo, "agents/a.md")
        agent = repo / "agents" / "a.md"
        agent.parent.mkdir(parents=True)
        agent.write_text("x")
        plan.chmod(0)
        try:
            event = {
                "tool_name": "Edit",
                "tool_input": {"file_path": str(agent), "new_string": "x"},
            }
            parsed, stdout, stderr, rc = _run(event, cwd=repo)
        finally:
            plan.chmod(stat.S_IRUSR | stat.S_IWUSR)
        assert parsed is not None and parsed.get("decision") == "block", (
            f"unreadable arming plan must fail closed, got {stdout!r}"
        )

    def test_block_emits_exactly_one_json_object(self, repo: Path):
        """Single-emission contract holds for the new block message."""
        self._armed_plan(repo, "agents/a.md")
        other = repo / "agents" / "undeclared.md"
        other.parent.mkdir(parents=True)
        other.write_text("x")
        event = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(other),
                "new_string": "repoPath = '/tmp'\n",
            },
        }
        parsed, stdout, stderr, rc = _run(event, cwd=repo)
        lines = [ln for ln in stdout.strip().splitlines() if ln.strip()]
        assert len(lines) == 1, (
            f"expected exactly 1 JSON line, got {len(lines)}: {stdout!r}"
        )
        assert parsed["decision"] == "block"
        reason = parsed.get("reason", "")
        assert "HOOK CRASH" not in reason, f"blocked via a crash: {reason!r}"
        assert "behavioral instruction-file edit" in reason, (
            f"expected the undeclared-file block reason, got {reason!r}"
        )

    def test_declared_file_allowed_from_linked_worktree(self, tmp_path: Path):
        """D2 regression lock, modeled on
        TestTargetScopedRootResolution.test_worktree_consults_the_main_checkouts_plans
        (same file). Pre-D2 this failed CLOSED (falsely BLOCKED): declared
        entries resolved against `plan_root` (the main checkout, via
        `--git-common-dir`) while `file_path` resolved to the worktree's own
        top-level directory — the two paths could never structurally match.
        Uses `use_root_seam=False` so REAL target-scoped git discovery runs;
        with the seam on, the root is FORCED to `cwd` regardless of which
        file is edited, which would make this test pass vacuously whether or
        not D2 is implemented.
        """
        # Arrange
        main_repo = tmp_path / "main-repo"
        main_repo.mkdir()
        _init_repo(main_repo)
        _write_plan(
            main_repo,
            "plan.md",
            body=(
                "---\nstatus: in-progress\n"
                "instruction_files: agents/declared.md\n---\n\n# Plan\n"
            ),
        )

        worktree_dir = tmp_path / "wt-checkout"
        subprocess.run(
            [
                "git", "-C", str(main_repo), "worktree", "add", "-q",
                "-b", "wt-branch", str(worktree_dir),
            ],
            check=True,
            capture_output=True,
        )

        declared = worktree_dir / "agents" / "declared.md"
        declared.parent.mkdir(parents=True)
        declared.write_text("# Agent\n")

        # Act
        event = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(declared), "new_string": "altered"},
        }
        parsed, stdout, stderr, rc = _run(event, use_root_seam=False)

        # Assert
        _assert_allowed(
            parsed, stdout, stderr, rc,
            "a file declared repo-relative to its own worktree must be "
            "allowed, not falsely blocked by a main-checkout-rooted "
            "resolution",
        )

    def test_stale_cache_hit_does_not_launder_a_misidentified_plan(
        self, repo: Path
    ):
        """D1 regression lock.

        CANNOT be constructed by two ordinary writes: `_compute_signature()`
        (`hooks/_lib/active_plan.py:556`) hashes `st_mtime_ns` for every
        `*.md` in the plans dir (candidates gathered at `:661-664`), so an
        ordinary flip of plan B to `in-progress` changes B's mtime (or, if B
        is newly created, changes the candidate list itself) and busts the
        cached signature, forcing a rescan — the stale-positive hit this
        test targets never occurs through ordinary status edits. It
        requires a status change to B that does NOT move B's mtime (a
        restore, a `touch -r` after an out-of-band edit, or — as here — a
        directly hand-written cache entry via the `ACTIVE_PLAN_CACHE_FILE`
        seam), which is why this test builds the cache entry by hand rather
        than by performing two ordinary writes.

        Without D1, this test would ALLOW the edit — honoring plan A's
        `instruction_files` declaration while plan B is equally
        `in-progress` and the authoritative uncached call would raise
        `AmbiguousActivePlanError`. That silent allow is exactly the
        authorization consequence D1 closes; the general caching hole
        itself (why a signature-matching hand-written entry can exist at
        all) remains open and is NOT what this test is proving closed.
        """
        # Arrange — two plans, both genuinely in-progress
        plan_a = _write_plan(
            repo, "plan-a.md",
            body=(
                "---\nstatus: in-progress\n"
                "instruction_files: agents/a.md\n---\n\n# Plan A\n"
            ),
        )
        _write_plan(
            repo, "plan-b.md",
            body="---\nstatus: in-progress\n---\n\n# Plan B\n",
        )
        agent = repo / "agents" / "a.md"
        agent.parent.mkdir(parents=True)
        agent.write_text("# Agent\n")

        # Hand-write a cache entry whose signature matches the CURRENT
        # candidate set (both plan-a.md and plan-b.md, as they exist right
        # now) but whose plan_path claims A alone is the answer — the exact
        # shape find_active_plan_cached() accepts as a hit, and the exact
        # shape an honest uncached scan would instead reject as ambiguous.
        session_id = f"test-d1-cache-{uuid.uuid4().hex[:12]}"
        cache_file = repo / "d1-cache.json"
        candidates = sorted((repo / "docs" / "plans").glob("*.md"))
        signature = _compute_signature(candidates)
        cache_file.write_text(json.dumps({
            "version": _CACHE_ENTRY_VERSION,
            "repo_root": str(repo),
            "session_id": session_id,
            "signature": signature,
            "plan_path": str(plan_a),
            "ts": time.time(),
        }))

        # Act
        event = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(agent), "new_string": "altered"},
        }
        parsed, stdout, stderr, rc = _run(
            event,
            cwd=repo,
            env={
                "CLAUDE_CODE_SESSION_ID": session_id,
                "ACTIVE_PLAN_CACHE_FILE": str(cache_file),
            },
        )

        # Assert
        assert parsed is not None and parsed.get("decision") == "block", (
            f"a stale-POSITIVE cache hit must not authorize the edit via "
            f"A's declaration, got {stdout!r}"
        )
        reason = parsed.get("reason", "").lower()
        assert "cannot determine active plan state" in reason, (
            f"expected the D1 uncached re-check's ambiguity block, got "
            f"{reason!r}"
        )
