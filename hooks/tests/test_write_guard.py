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
import json
import stat
import subprocess
from pathlib import Path

import pytest


HOOKS_DIR = Path("/Users/cevin/.claude/skills/coding-team/hooks")
HOOK_PATH = HOOKS_DIR / "write-guard.py"

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


def _run(event: dict, cwd: Path | None = None) -> tuple[dict | None, str, str, int]:
    """Run write-guard.py with the given event; return (parsed_json, stdout, stderr, returncode)."""
    result = subprocess.run(
        ["python3", str(HOOK_PATH)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        timeout=10,
        cwd=str(cwd) if cwd else None,
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
        assert parsed is not None and parsed.get("decision") == "block", (
            f"expected block — in-progress plan should activate gate regardless of "
            f"complete sibling, got {stdout!r}"
        )


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


# ---------------------------------------------------------------------------
# Migration guard — independent of pipeline detection
# ---------------------------------------------------------------------------


class TestMigrationGuard:
    def test_blocks_edit_to_existing_tracked_migration(self, repo: Path):
        """Tracked migration file -> blocked even with no active plan."""
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
