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
    """Return env dict with a unique test session ID and a per-test cache file.

    Also pins CODING_TEAM_MAIN_ROOT to tmp_path (the same path the `repo`
    fixture initializes as a git repo) so active-plan detection uses the
    test repo directly instead of depending on `git rev-parse` succeeding
    in an ephemeral tmp repo (see _lib/active_plan.py). CODING_TEAM_TEST_SEAM
    must be paired with it (P1-5) — without the sentinel, the override is
    ignored and these tests would depend on real git discovery instead.
    """
    session_id = f"test-active-plan-{uuid.uuid4().hex[:12]}"
    cache_file = tmp_path / "active-plan-cache.json"
    return {
        "CLAUDE_CODE_SESSION_ID": session_id,
        "ACTIVE_PLAN_CACHE_FILE": str(cache_file),
        "CODING_TEAM_MAIN_ROOT": str(tmp_path),
        "CODING_TEAM_TEST_SEAM": "1",
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

def _counting(counter_path=counter_path, _orig=_original, **kwargs):
    result = _orig(**kwargs)
    count = json.loads(counter_path.read_text())
    counter_path.write_text(json.dumps(count + 1))
    return result

# mock-ok: real counting side-channel wrapper around the REAL
# find_active_plan (still calls _orig(**kwargs) and returns its actual
# result) — not a behavior stub. See the module docstring's "sentinel
# counter pattern".
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

def _counting(counter_path=counter_path, _orig=_original, **kwargs):
    result = _orig(**kwargs)
    count = json.loads(counter_path.read_text())
    counter_path.write_text(json.dumps(count + 1))
    return result

# mock-ok: real counting side-channel wrapper around the REAL
# find_active_plan (still calls _orig(**kwargs) and returns its actual
# result) — not a behavior stub. See the module docstring's "sentinel
# counter pattern".
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
        reason = parsed.get("reason", "")
        assert "HOOK CRASH" not in reason, f"block came from a hook crash: {parsed!r}"
        reason_lower = reason.lower()
        assert "instruction file" in reason_lower or "in-progress" in reason_lower

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

    def test_no_plan_result_is_never_cached_always_rescans(self, repo: Path, session_env: dict):
        """P1-4: a None result (no active plan) must NEVER be cached — it is
        the DISARMED answer, and caching it risks serving a stale None while
        a plan is actually armed (see TestNegativeResultNotCached). Every
        call with no active plan must rescan, not just the first."""
        counter_file = Path(session_env["ACTIVE_PLAN_CACHE_FILE"]).parent / "counter2.json"
        counter_file.write_text("0")

        code_call1 = f"""
import json
from pathlib import Path
from _lib.active_plan import find_active_plan_cached
import _lib.active_plan as _ap
_original = _ap.find_active_plan

def _counting(_orig=_original, **kwargs):
    result = _orig(**kwargs)
    counter = Path({str(counter_file)!r})
    c = json.loads(counter.read_text())
    counter.write_text(json.dumps(c + 1))
    return result

# mock-ok: real counting side-channel wrapper around the REAL
# find_active_plan (still calls _orig(**kwargs) and returns its actual
# result) — not a behavior stub. See the module docstring's "sentinel
# counter pattern".
_ap.find_active_plan = _counting
result = find_active_plan_cached(ttl_seconds=60)
print(json.dumps({{"plan": str(result) if result else None}}))
"""
        r1 = run_python(code_call1, cwd=repo, env=session_env)
        assert r1.returncode == 0, r1.stderr
        out1 = json.loads(r1.stdout)
        assert out1["plan"] is None

        # Call 2: must rescan again — a None result is never written to the
        # cache file, so there is nothing for call 2 to hit.
        code_call2 = f"""
import json
from pathlib import Path
from _lib.active_plan import find_active_plan_cached
import _lib.active_plan as _ap
_original = _ap.find_active_plan

def _counting(_orig=_original, **kwargs):
    result = _orig(**kwargs)
    counter = Path({str(counter_file)!r})
    c = json.loads(counter.read_text())
    counter.write_text(json.dumps(c + 1))
    return result

# mock-ok: real counting side-channel wrapper around the REAL
# find_active_plan (still calls _orig(**kwargs) and returns its actual
# result) — not a behavior stub. See the module docstring's "sentinel
# counter pattern".
_ap.find_active_plan = _counting
result = find_active_plan_cached(ttl_seconds=60)
print(json.dumps({{"plan": str(result) if result else None}}))
"""
        r2 = run_python(code_call2, cwd=repo, env=session_env)
        assert r2.returncode == 0, r2.stderr
        out2 = json.loads(r2.stdout)
        assert out2["plan"] is None

        count_after_call2 = json.loads(counter_file.read_text())
        assert count_after_call2 == 2, (
            f"a None result must never be cached — expected a rescan on every "
            f"call (2 scans across 2 calls), got {count_after_call2}"
        )

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

def _counting(_orig=_original, **kwargs):
    result = _orig(**kwargs)
    counter = Path({str(counter_file)!r})
    c = json.loads(counter.read_text())
    counter.write_text(json.dumps(c + 1))
    return result

# mock-ok: real counting side-channel wrapper around the REAL
# find_active_plan (still calls _orig(**kwargs) and returns its actual
# result) — not a behavior stub. See the module docstring's "sentinel
# counter pattern".
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
            "CODING_TEAM_MAIN_ROOT": str(repo),
            "CODING_TEAM_TEST_SEAM": "1",
        }
        session_env2 = {
            "CLAUDE_CODE_SESSION_ID": f"session-B-{uuid.uuid4().hex[:8]}",
            "ACTIVE_PLAN_CACHE_FILE": str(cache_file2),
            "CODING_TEAM_MAIN_ROOT": str(repo),
            "CODING_TEAM_TEST_SEAM": "1",
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


class TestNegativeResultNotCached:
    """P1-4: a None result (no active plan) must never be served stale, and
    a hand-written or legacy cache entry must not be able to fake a cached
    None (or a never-expiring positive entry) past the reader's validation.
    Caching only positive results means the worst stale case is a needless
    block (fail-closed), not a silent allow — see the producer-side lock
    below and TestCrossInvocationCache.test_no_plan_result_is_never_cached_always_rescans.
    """

    def test_stale_none_is_not_served_after_status_flip(
        self, repo: Path, tmp_path: Path, session_env: dict
    ):
        """Producer-side lock. Prime the cache with status: planned (None),
        flip the SAME file to in-progress, then restore the ORIGINAL mtime —
        defeating the signature-based invalidation the same way Codex
        reproduced the disarm. A call within the TTL must NOT return the
        stale cached None."""
        plan = _write_plan(repo, "plan.md", PLANNED_FRONTMATTER + "# Plan\n")
        original_stat = plan.stat()

        code_call1 = """
import json
from _lib.active_plan import find_active_plan_cached
result = find_active_plan_cached(ttl_seconds=60)
print(json.dumps({"plan": str(result) if result else None}))
"""
        r1 = run_python(code_call1, cwd=repo, env=session_env)
        assert r1.returncode == 0, f"call 1 failed: {r1.stderr}"
        out1 = json.loads(r1.stdout)
        assert out1["plan"] is None, f"planned status should yield None, got {out1['plan']}"

        # Flip to in-progress, then restore the ORIGINAL mtime/atime so a
        # signature comparison alone cannot see the change.
        plan.write_text(
            ACTIVE_FRONTMATTER + "# Plan\n\n## Completion Checklist\n- [ ] Second-opinion review\n"
        )
        os.utime(plan, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))

        code_call2 = """
import json
from _lib.active_plan import find_active_plan_cached
result = find_active_plan_cached(ttl_seconds=60)
print(json.dumps({"plan": str(result) if result else None}))
"""
        r2 = run_python(code_call2, cwd=repo, env=session_env)
        assert r2.returncode == 0, f"call 2 failed: {r2.stderr}"
        out2 = json.loads(r2.stdout)
        assert out2["plan"] is not None, (
            "SAFETY FAILURE: a None cached from call 1 was served stale after "
            "a mtime-preserving flip to in-progress — write-guard would stay "
            "DISARMED while a plan is armed."
        )
        assert str(plan) in out2["plan"], f"expected plan path {plan!s}, got {out2['plan']}"

    def test_handwritten_null_plan_path_is_a_cache_miss(
        self, repo: Path, tmp_path: Path, session_env: dict
    ):
        """A hand-written (or legacy-writer-produced) cache entry with
        plan_path=null, otherwise fully valid (current version, matching
        signature, unexpired ts), must be treated as a cache MISS — a
        write-side-only fix (never WRITE a null plan_path) would still let
        a reader SERVE one from a hand-written or externally redirected
        cache file (ACTIVE_PLAN_CACHE_FILE)."""
        plan = _write_plan(repo, "plan.md")  # in-progress by default

        code = f"""
import json, time
from pathlib import Path
import _lib.active_plan as _ap

plan_root = Path({str(repo)!r})
plans_dir = plan_root / "docs" / "plans"
candidates = sorted(plans_dir.glob("*.md"))
sig = _ap._compute_signature(candidates)

entry = {{
    "version": _ap._CACHE_ENTRY_VERSION,
    "repo_root": str(plan_root),
    "session_id": {session_env["CLAUDE_CODE_SESSION_ID"]!r},
    "signature": sig,
    "plan_path": None,
    "ts": time.time(),
}}
Path({str(Path(session_env["ACTIVE_PLAN_CACHE_FILE"]))!r}).write_text(json.dumps(entry))

result = _ap.find_active_plan_cached(ttl_seconds=60)
print(json.dumps({{"plan": str(result) if result else None}}))
"""
        r = run_python(code, cwd=repo, env=session_env)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout)
        assert out["plan"] is not None, (
            f"a hand-written plan_path=null entry must be a cache miss "
            f"(fresh scan), not served as a cached None: {out!r}"
        )
        assert str(plan) in out["plan"]

    def test_legacy_entry_without_version_is_rejected(
        self, repo: Path, tmp_path: Path, session_env: dict
    ):
        """A cache entry lacking the version field (the pre-P1-4 shape,
        possibly holding a stale negative result written before this fix
        existed) must be rejected outright — cache miss, forcing a rescan.
        Uses a POSITIVE stored plan_path so the test proves rejection rather
        than coincidentally matching a fresh scan's result for the wrong
        reason."""
        plan = _write_plan(repo, "plan.md")
        counter_file = tmp_path / "counter_legacy.json"
        counter_file.write_text("0")

        code = f"""
import json, time
from pathlib import Path
import _lib.active_plan as _ap

plan_root = Path({str(repo)!r})
plans_dir = plan_root / "docs" / "plans"
candidates = sorted(plans_dir.glob("*.md"))
sig = _ap._compute_signature(candidates)

# Legacy shape: no "version" key at all.
entry = {{
    "repo_root": str(plan_root),
    "session_id": {session_env["CLAUDE_CODE_SESSION_ID"]!r},
    "signature": sig,
    "plan_path": {str(plan)!r},
    "ts": time.time(),
}}
Path({str(Path(session_env["ACTIVE_PLAN_CACHE_FILE"]))!r}).write_text(json.dumps(entry))

counter_path = Path({str(counter_file)!r})
_original = _ap.find_active_plan
def _counting(_orig=_original, **kwargs):
    result = _orig(**kwargs)
    c = json.loads(counter_path.read_text())
    counter_path.write_text(json.dumps(c + 1))
    return result
# mock-ok: real counting side-channel wrapper around the REAL
# find_active_plan (still calls _orig(**kwargs) and returns its actual
# result) — not a behavior stub. See the module docstring's "sentinel
# counter pattern".
_ap.find_active_plan = _counting

result = _ap.find_active_plan_cached(ttl_seconds=60)
print(json.dumps({{"plan": str(result) if result else None}}))
"""
        r = run_python(code, cwd=repo, env=session_env)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout)
        assert out["plan"] is not None and str(plan) in out["plan"]

        count = json.loads(counter_file.read_text())
        assert count == 1, (
            f"a version-less legacy cache entry must be rejected (cache miss, "
            f"triggering a rescan), got {count} rescans"
        )

    def test_future_timestamp_entry_is_rejected(
        self, repo: Path, tmp_path: Path, session_env: dict
    ):
        """A cache entry whose ts is ahead of `now` must be rejected — the
        TTL check `now - ts < ttl_seconds` alone ACCEPTS a future ts (the
        subtraction goes negative, which is always < ttl_seconds), so a
        far-future ts would never expire without an explicit bound."""
        plan = _write_plan(repo, "plan.md")
        counter_file = tmp_path / "counter_future.json"
        counter_file.write_text("0")

        code = f"""
import json, time
from pathlib import Path
import _lib.active_plan as _ap

plan_root = Path({str(repo)!r})
plans_dir = plan_root / "docs" / "plans"
candidates = sorted(plans_dir.glob("*.md"))
sig = _ap._compute_signature(candidates)

entry = {{
    "version": _ap._CACHE_ENTRY_VERSION,
    "repo_root": str(plan_root),
    "session_id": {session_env["CLAUDE_CODE_SESSION_ID"]!r},
    "signature": sig,
    "plan_path": {str(plan)!r},
    "ts": time.time() + 1_000_000_000,
}}
Path({str(Path(session_env["ACTIVE_PLAN_CACHE_FILE"]))!r}).write_text(json.dumps(entry))

counter_path = Path({str(counter_file)!r})
_original = _ap.find_active_plan
def _counting(_orig=_original, **kwargs):
    result = _orig(**kwargs)
    c = json.loads(counter_path.read_text())
    counter_path.write_text(json.dumps(c + 1))
    return result
# mock-ok: real counting side-channel wrapper around the REAL
# find_active_plan (still calls _orig(**kwargs) and returns its actual
# result) — not a behavior stub. See the module docstring's "sentinel
# counter pattern".
_ap.find_active_plan = _counting

result = _ap.find_active_plan_cached(ttl_seconds=60)
print(json.dumps({{"plan": str(result) if result else None}}))
"""
        r = run_python(code, cwd=repo, env=session_env)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout)
        assert out["plan"] is not None and str(plan) in out["plan"]

        count = json.loads(counter_file.read_text())
        assert count == 1, (
            f"an entry with a future ts must be rejected (cache miss, "
            f"triggering a rescan), got {count} rescans"
        )


class TestResolveTargetGitRootsRejectsRelativePaths:
    """P3-A: a relative file_path must not fall back to cwd-scoped
    resolution. Without this guard, the ancestor walk in
    _resolve_target_git_roots() would land on Path(".") for a relative
    input, and `git -C .` would then run against the PROCESS's cwd —
    reintroducing the exact cwd-scoped defect this function exists to
    close (P1-5). Not reachable through the real Edit/Write client (its
    file_path is always absolute), but defended anyway.
    """

    def test_relative_path_returns_none_none_regardless_of_armed_cwd(self, repo: Path):
        """cwd is a real, armed git repo — if the guard were absent, a
        relative file_path would resolve INTO this repo via cwd. No
        CODING_TEAM_TEST_SEAM is set, so real git discovery actually runs.
        """
        _write_plan(repo, "plan.md")
        code = """
import json
from _lib.active_plan import _resolve_target_git_roots
worktree_root, plan_root = _resolve_target_git_roots("hooks/x.py")
print(json.dumps({
    "worktree_root": str(worktree_root) if worktree_root else None,
    "plan_root": str(plan_root) if plan_root else None,
}))
"""
        r = run_python(code, cwd=repo)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout)
        assert out["worktree_root"] is None, (
            f"a relative file_path must not resolve via cwd, got {out!r}"
        )
        assert out["plan_root"] is None, (
            f"a relative file_path must not resolve via cwd, got {out!r}"
        )


class TestCacheFileKeyedByPlanRoot:
    """P3-B: the cache filename is keyed by a hash of plan_root, so
    alternating lookups between two different repos don't evict each
    other's entry. A single shared filename would: the cache entry holds
    only ONE result at a time and every write overwrites the whole file,
    so alternating repos would thrash — each call's miss evicting the
    other repo's just-written entry.
    """

    def test_different_plan_roots_get_different_cache_files(self):
        code = """
import json
from pathlib import Path
from _lib.active_plan import _cache_file_path
p1 = _cache_file_path(Path("/some/repo-a"))
p2 = _cache_file_path(Path("/some/repo-b"))
p1_again = _cache_file_path(Path("/some/repo-a"))
print(json.dumps({"p1": str(p1), "p2": str(p2), "p1_again": str(p1_again)}))
"""
        r = run_python(code)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout)
        assert out["p1"] != out["p2"], (
            f"different plan_roots must get different cache files, got {out!r}"
        )
        assert out["p1"] == out["p1_again"], (
            f"the same plan_root must consistently map to the same cache file, got {out!r}"
        )


class TestMainRootTestSeamPairing:
    """P1-5: CODING_TEAM_MAIN_ROOT must be honored only when paired with a
    truthy CODING_TEAM_TEST_SEAM — an ambient leftover of the former alone
    must degrade to real git discovery, not silently redirect the root."""

    def test_main_root_override_ignored_without_sentinel(self, tmp_path: Path):
        """Without CODING_TEAM_TEST_SEAM, CODING_TEAM_MAIN_ROOT is ignored."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        code = """
import json
from _lib.active_plan import _git_main_root
result = _git_main_root()
print(json.dumps({"root": str(result) if result else None}))
"""
        r = run_python(code, cwd=tmp_path, env={"CODING_TEAM_MAIN_ROOT": str(empty_dir)})
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout)
        assert out["root"] != str(empty_dir), (
            "CODING_TEAM_MAIN_ROOT must be ignored when CODING_TEAM_TEST_SEAM "
            "is not set — an ambient leftover must not silently redirect the root"
        )

    def test_main_root_override_honored_with_sentinel(self, tmp_path: Path):
        """With the paired CODING_TEAM_TEST_SEAM=1 sentinel, the override IS honored.

        Regression lock, not a red test: this passes both before and after
        the P1-5 fix — only test_main_root_override_ignored_without_sentinel
        above is new coverage of the actual defect.
        """
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        code = """
import json
from _lib.active_plan import _git_main_root
result = _git_main_root()
print(json.dumps({"root": str(result) if result else None}))
"""
        r = run_python(
            code,
            cwd=tmp_path,
            env={"CODING_TEAM_MAIN_ROOT": str(empty_dir), "CODING_TEAM_TEST_SEAM": "1"},
        )
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout)
        assert out["root"] == str(empty_dir)
