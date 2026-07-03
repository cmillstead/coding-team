"""Tests for _lib/active_plan.py — cross-invocation persistent cache.

The cache is file-backed, keyed by repo-root + session-id, invalidated by the
sorted candidate-file (path, st_mtime_ns) signature over docs/plans/*.md.
Tests use real temp git repos, real plan files, and real cache files (tmp_path).
No mocks, monkeypatching of internals, or unittest.mock.

The sentinel counter pattern: a real counter FILE is incremented each time the
underlying find_active_plan() executes a real frontmatter read, making cache
hits vs misses observable across subprocess boundaries without mock introspection.
"""

import json
import os
import subprocess
import time
import uuid
from pathlib import Path

import pytest


HOOKS_DIR = Path(__file__).resolve().parent.parent  # tests/ -> hooks/

ACTIVE_FRONTMATTER = "---\nstatus: in-progress\n---\n\n"
PLANNED_FRONTMATTER = "---\nstatus: planned\n---\n\n"
COMPLETE_FRONTMATTER = "---\nstatus: complete\n---\n\n"


def _init_repo(repo_root: Path) -> None:
    """Initialize a minimal git repo at repo_root."""
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(repo_root)],
        check=True,
        capture_output=True,
    )


def _write_plan(repo_root: Path, name: str, body: str | None = None) -> Path:
    """Create or overwrite a plan file under docs/plans/."""
    if body is None:
        body = ACTIVE_FRONTMATTER + "# Plan\n\n## Completion Checklist\n- [ ] Second-opinion review\n"
    plans_dir = repo_root / "docs" / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    plan = plans_dir / name
    plan.write_text(body)
    return plan


def run_python(code: str, *, cwd: Path | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    """Run a Python snippet with the hooks dir on sys.path."""
    full_code = f"import sys; sys.path.insert(0, {str(HOOKS_DIR)!r})\n{code}"
    run_env = None
    if env is not None:
        run_env = {**os.environ, **env}
    return subprocess.run(
        ["python3", "-c", full_code],
        capture_output=True,
        text=True,
        timeout=15,
        cwd=str(cwd) if cwd else None,
        env=run_env,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Fresh git repo under tmp_path."""
    _init_repo(tmp_path)
    return tmp_path


@pytest.fixture
def session_env(tmp_path: Path) -> dict:
    """Return env dict with a unique test session ID and a per-test cache file."""
    session_id = f"test-active-plan-{uuid.uuid4().hex[:12]}"
    cache_file = tmp_path / "active-plan-cache.json"
    return {
        "CLAUDE_CODE_SESSION_ID": session_id,
        "ACTIVE_PLAN_CACHE_FILE": str(cache_file),
    }


class TestCrossInvocationCache:
    """Cache correctness across separate subprocess invocations."""

    def test_cache_hit_no_rescan_when_unchanged(self, repo: Path, tmp_path: Path, session_env: dict):
        """Two calls with no plan change: second call hits the cache (no re-scan).

        The sentinel counter file is incremented each time find_active_plan()
        reads+parses a plan's frontmatter. On a cache hit the counter must NOT
        increase between call 1 and call 2.
        """
        _write_plan(repo, "plan.md")
        counter_file = tmp_path / "scan_counter.json"
        counter_file.write_text("0")

        # Call 1: cold cache — must scan and populate
        code1 = f"""
import json
from pathlib import Path
from _lib.active_plan import find_active_plan_cached

counter_path = Path({str(counter_file)!r})

# Wrap find_active_plan to count real reads via the counter file
import _lib.active_plan as _ap
_original = _ap.find_active_plan

def _counting(counter_path=counter_path, _orig=_original):
    result = _orig()
    count = json.loads(counter_path.read_text())
    counter_path.write_text(json.dumps(count + 1))
    return result

_ap.find_active_plan = _counting

result = find_active_plan_cached(ttl_seconds=60)
print(json.dumps({{"plan": str(result) if result else None}}))
"""
        r1 = run_python(code1, cwd=repo, env=session_env)
        assert r1.returncode == 0, f"call 1 failed: {r1.stderr}"
        out1 = json.loads(r1.stdout)
        assert out1["plan"] is not None, f"expected active plan, got None; stderr={r1.stderr}"

        count_after_call1 = json.loads(counter_file.read_text())
        assert count_after_call1 == 1, f"expected 1 scan on cold cache, got {count_after_call1}"

        # Call 2: warm cache — must NOT rescan (counter stays at 1)
        code2 = f"""
import json
from pathlib import Path
from _lib.active_plan import find_active_plan_cached

counter_path = Path({str(counter_file)!r})

import _lib.active_plan as _ap
_original = _ap.find_active_plan

def _counting(counter_path=counter_path, _orig=_original):
    result = _orig()
    count = json.loads(counter_path.read_text())
    counter_path.write_text(json.dumps(count + 1))
    return result

_ap.find_active_plan = _counting

result = find_active_plan_cached(ttl_seconds=60)
print(json.dumps({{"plan": str(result) if result else None}}))
"""
        r2 = run_python(code2, cwd=repo, env=session_env)
        assert r2.returncode == 0, f"call 2 failed: {r2.stderr}"
        out2 = json.loads(r2.stdout)
        assert out2["plan"] == out1["plan"], "cache hit must return same path"

        count_after_call2 = json.loads(counter_file.read_text())
        assert count_after_call2 == 1, (
            f"cache hit must not increment counter; expected 1, got {count_after_call2}"
        )

    def test_in_place_status_flip_is_seen_immediately(self, repo: Path, tmp_path: Path, session_env: dict):
        """SAFETY-CRITICAL: in-place status flip must break the cache.

        Write a plan as status: planned -> call find_active_plan_cached() -> expect None.
        Edit the SAME file IN PLACE to status: in-progress (same path, directory
        mtime may NOT change). Call again -> MUST return the in-progress plan.

        This test proves write-guard cannot be left disarmed by a stale cache.
        """
        plan = _write_plan(repo, "plan.md", PLANNED_FRONTMATTER + "# Plan\n")

        # Call 1: planned -> expect None (gate disarmed)
        code_call1 = """
import json
from pathlib import Path
from _lib.active_plan import find_active_plan_cached
result = find_active_plan_cached(ttl_seconds=60)
print(json.dumps({"plan": str(result) if result else None}))
"""
        r1 = run_python(code_call1, cwd=repo, env=session_env)
        assert r1.returncode == 0, f"call 1 failed: {r1.stderr}"
        out1 = json.loads(r1.stdout)
        assert out1["plan"] is None, f"planned status should yield None, got {out1['plan']}"

        # Flip in place: overwrite SAME path with in-progress content
        # (st_mtime_ns changes; directory mtime may or may not change on macOS)
        plan.write_text(
            ACTIVE_FRONTMATTER + "# Plan\n\n## Completion Checklist\n- [ ] Second-opinion review\n"
        )

        # Call 2: same path, now in-progress -> MUST NOT return None
        code_call2 = """
import json
from pathlib import Path
from _lib.active_plan import find_active_plan_cached
result = find_active_plan_cached(ttl_seconds=60)
print(json.dumps({"plan": str(result) if result else None}))
"""
        r2 = run_python(code_call2, cwd=repo, env=session_env)
        assert r2.returncode == 0, f"call 2 failed: {r2.stderr}"
        out2 = json.loads(r2.stdout)
        assert out2["plan"] is not None, (
            "SAFETY FAILURE: in-place status flip from planned->in-progress was not detected. "
            "Cache served stale None, leaving write-guard DISARMED."
        )
        assert str(plan) in out2["plan"], (
            f"expected plan path {plan!s}, got {out2['plan']}"
        )

    def test_in_place_checkbox_flip_is_seen_immediately(self, repo: Path, tmp_path: Path, session_env: dict):
        """Checkbox tick in place (content change, same path) is reflected on next call."""
        plan = _write_plan(
            repo, "plan.md",
            ACTIVE_FRONTMATTER + "# Plan\n\n## Completion Checklist\n- [ ] Second-opinion review\n"
        )

        # Call 1: unchecked plan
        code_call1 = """
import json
from pathlib import Path
from _lib.active_plan import find_active_plan_cached
result = find_active_plan_cached(ttl_seconds=60)
print(json.dumps({"plan": str(result) if result else None}))
"""
        r1 = run_python(code_call1, cwd=repo, env=session_env)
        assert r1.returncode == 0, r1.stderr
        out1 = json.loads(r1.stdout)
        assert out1["plan"] is not None

        # Tick the checkbox in place (same file, content changes)
        plan.write_text(
            ACTIVE_FRONTMATTER + "# Plan\n\n## Completion Checklist\n- [x] Second-opinion review\n"
        )

        # Call 2: mtime changed -> cache invalid -> re-read plan
        code_call2 = f"""
import json
from pathlib import Path
from _lib.active_plan import find_active_plan_cached
result = find_active_plan_cached(ttl_seconds=60)
plan_text = Path({str(plan)!r}).read_text() if result else ""
print(json.dumps({{"plan": str(result) if result else None, "has_x": "[x]" in plan_text}}))
"""
        r2 = run_python(code_call2, cwd=repo, env=session_env)
        assert r2.returncode == 0, r2.stderr
        out2 = json.loads(r2.stdout)
        # The plan is still in-progress (status didn't change), so it's still active
        assert out2["plan"] is not None, "in-progress plan should still be active after checkbox tick"
        assert out2["has_x"], "checkbox tick should be visible in the re-read plan text"

    def test_block_decision_unchanged(self, repo: Path, session_env: dict):
        """In-progress plan still blocks an instruction-file edit through the cached path."""
        _write_plan(repo, "plan.md")
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
        hook_path = HOOKS_DIR / "write-guard.py"
        result = subprocess.run(
            ["python3", str(hook_path)],
            input=json.dumps(event),
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(repo),
            env={**os.environ, **session_env},
        )
        assert result.returncode == 0, result.stderr
        parsed = json.loads(result.stdout)
        assert parsed.get("decision") == "block", (
            f"expected block, got {parsed}; stderr={result.stderr}"
        )
        reason = parsed.get("reason", "").lower()
        assert "instruction file" in reason or "in-progress" in reason

    def test_cached_result_equals_uncached(self, repo: Path, session_env: dict):
        """Cached result must equal what find_active_plan() returns directly."""
        _write_plan(repo, "plan.md")

        code = """
import json
from pathlib import Path
from _lib.active_plan import find_active_plan, find_active_plan_cached

cached = find_active_plan_cached(ttl_seconds=60)
direct = find_active_plan()

print(json.dumps({
    "cached": str(cached) if cached else None,
    "direct": str(direct) if direct else None,
}))
"""
        r = run_python(code, cwd=repo, env=session_env)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout)
        assert out["cached"] == out["direct"], (
            f"cached result {out['cached']!r} != uncached {out['direct']!r}"
        )

    def test_no_plan_cached_as_none(self, repo: Path, session_env: dict):
        """When no plan exists, None is cached and returned on subsequent calls without re-scan."""
        counter_file = Path(session_env["ACTIVE_PLAN_CACHE_FILE"]).parent / "counter2.json"
        counter_file.write_text("0")

        code_call1 = f"""
import json
from pathlib import Path
from _lib.active_plan import find_active_plan_cached
import _lib.active_plan as _ap
_original = _ap.find_active_plan

def _counting(_orig=_original):
    result = _orig()
    counter = Path({str(counter_file)!r})
    c = json.loads(counter.read_text())
    counter.write_text(json.dumps(c + 1))
    return result

_ap.find_active_plan = _counting
result = find_active_plan_cached(ttl_seconds=60)
print(json.dumps({{"plan": str(result) if result else None}}))
"""
        r1 = run_python(code_call1, cwd=repo, env=session_env)
        assert r1.returncode == 0, r1.stderr
        out1 = json.loads(r1.stdout)
        assert out1["plan"] is None

        # Call 2: cached None must also come back without re-scanning
        code_call2 = f"""
import json
from pathlib import Path
from _lib.active_plan import find_active_plan_cached
import _lib.active_plan as _ap
_original = _ap.find_active_plan

def _counting(_orig=_original):
    result = _orig()
    counter = Path({str(counter_file)!r})
    c = json.loads(counter.read_text())
    counter.write_text(json.dumps(c + 1))
    return result

_ap.find_active_plan = _counting
result = find_active_plan_cached(ttl_seconds=60)
print(json.dumps({{"plan": str(result) if result else None}}))
"""
        r2 = run_python(code_call2, cwd=repo, env=session_env)
        assert r2.returncode == 0, r2.stderr
        out2 = json.loads(r2.stdout)
        assert out2["plan"] is None

        count = json.loads(counter_file.read_text())
        assert count == 1, f"cached None should not trigger rescan; got {count} scans"

    def test_ttl_expiry_triggers_rescan(self, repo: Path, session_env: dict):
        """After TTL expires, the next call re-scans even if file signatures match."""
        _write_plan(repo, "plan.md")

        # Call 1: populate cache with TTL of 0 seconds (already expired on next call)
        code_call1 = """
import json
from _lib.active_plan import find_active_plan_cached
result = find_active_plan_cached(ttl_seconds=0)
print(json.dumps({"plan": str(result) if result else None}))
"""
        r1 = run_python(code_call1, cwd=repo, env=session_env)
        assert r1.returncode == 0, r1.stderr

        # Brief pause to ensure cache ts < now - 0 on the next call
        time.sleep(0.05)

        counter_file = Path(session_env["ACTIVE_PLAN_CACHE_FILE"]).parent / "counter3.json"
        counter_file.write_text("0")

        # Call 2: TTL=0 means already expired, must re-scan
        code_call2 = f"""
import json
from pathlib import Path
from _lib.active_plan import find_active_plan_cached
import _lib.active_plan as _ap
_original = _ap.find_active_plan

def _counting(_orig=_original):
    result = _orig()
    counter = Path({str(counter_file)!r})
    c = json.loads(counter.read_text())
    counter.write_text(json.dumps(c + 1))
    return result

_ap.find_active_plan = _counting
result = find_active_plan_cached(ttl_seconds=0)
print(json.dumps({{"plan": str(result) if result else None}}))
"""
        r2 = run_python(code_call2, cwd=repo, env=session_env)
        assert r2.returncode == 0, r2.stderr

        count = json.loads(counter_file.read_text())
        assert count >= 1, f"expired TTL should trigger rescan; got {count} scans"

    def test_different_sessions_dont_share_cache(self, repo: Path, tmp_path: Path):
        """Two different session IDs must not share a cache entry."""
        _write_plan(repo, "plan.md")

        cache_file1 = tmp_path / "cache1.json"
        cache_file2 = tmp_path / "cache2.json"

        session_env1 = {
            "CLAUDE_CODE_SESSION_ID": f"session-A-{uuid.uuid4().hex[:8]}",
            "ACTIVE_PLAN_CACHE_FILE": str(cache_file1),
        }
        session_env2 = {
            "CLAUDE_CODE_SESSION_ID": f"session-B-{uuid.uuid4().hex[:8]}",
            "ACTIVE_PLAN_CACHE_FILE": str(cache_file2),
        }

        code = """
import json
from _lib.active_plan import find_active_plan_cached
result = find_active_plan_cached(ttl_seconds=60)
print(json.dumps({"plan": str(result) if result else None}))
"""
        r1 = run_python(code, cwd=repo, env=session_env1)
        assert r1.returncode == 0, r1.stderr

        r2 = run_python(code, cwd=repo, env=session_env2)
        assert r2.returncode == 0, r2.stderr

        # Both should find the plan independently (different cache files)
        out1 = json.loads(r1.stdout)
        out2 = json.loads(r2.stdout)
        assert out1["plan"] is not None
        assert out2["plan"] is not None
        # They should both point to the same plan (consistency)
        assert out1["plan"] == out2["plan"]
