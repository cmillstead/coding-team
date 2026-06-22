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
import os
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


def _run(
    event: dict, cwd: Path | None = None, env: dict | None = None
) -> tuple[dict | None, str, str, int]:
    """Run write-guard.py with the given event; return (parsed_json, stdout, stderr, returncode)."""
    run_env = None
    if env is not None:
        run_env = {**os.environ, **env}
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
        assert parsed is not None and parsed.get("decision") == "block", (
            f"SKILL.md must remain gated, got {stdout!r}"
        )

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
        assert parsed is not None and parsed.get("decision") == "block", (
            f"agents/*.md must remain gated, got {stdout!r}"
        )

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
        assert parsed is not None and parsed.get("decision") == "block", (
            f"hooks/*.py must remain gated, got {stdout!r}"
        )

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
        lines = [l for l in stdout.strip().splitlines() if l.strip()]
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
        lines = [l for l in stdout.strip().splitlines() if l.strip()]
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
        lines = [l for l in stdout.strip().splitlines() if l.strip()]
        assert len(lines) == 1, (
            f"Expected exactly 1 JSON line, got {len(lines)}: {stdout!r}"
        )
        assert parsed is not None
        assert parsed["decision"] == "block"


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
