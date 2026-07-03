"""TEMPORARY CI diagnostic — REMOVE after reading the runner facts.

Replicates a Phase5 write-guard scenario and, instead of asserting block,
fails with a message dumping the runner-side facts so we can see WHY
_git_main_root() resolves to None on CI even with the CODING_TEAM_MAIN_ROOT
seam set. Named test_zzz_* so it sorts last.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent.parent
HOOK_PATH = HOOKS_DIR / "write-guard.py"
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

ACTIVE_FM = "---\nstatus: in-progress\n---\n\n# Plan\n\n## Completion Checklist\n- [ ] Second-opinion review\n"


def test_ci_diag_dump(tmp_path: Path):
    repo = tmp_path
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True, capture_output=True)
    (repo / "docs" / "plans").mkdir(parents=True)
    plan = repo / "docs" / "plans" / "plan.md"
    plan.write_text(ACTIVE_FM)
    instr = repo / "skills" / "demo" / "SKILL.md"
    instr.parent.mkdir(parents=True)
    instr.write_text("---\n---\n# Demo\nYou are demo.\n")

    # Mirror test_write_guard._run exactly.
    run_env = dict(os.environ)
    run_env.setdefault("CODING_TEAM_MAIN_ROOT", str(repo))
    event = {"tool_name": "Edit",
             "tool_input": {"file_path": str(instr), "new_string": "altered"}}
    proc = subprocess.run(
        ["python3", str(HOOK_PATH)], input=json.dumps(event),
        capture_output=True, text=True, timeout=10, cwd=str(repo), env=run_env,
    )

    # Raw git rev-parse in cwd=repo, same env the subprocess got.
    gitr = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=str(repo), capture_output=True, text=True, env=run_env,
    )

    # What _git_main_root() computes in THIS process with the same env.
    from _lib.active_plan import _git_main_root, find_active_plan
    old = os.environ.get("CODING_TEAM_MAIN_ROOT")
    os.environ["CODING_TEAM_MAIN_ROOT"] = str(repo)
    try:
        gmr = _git_main_root()
        fap = find_active_plan()
    finally:
        if old is None:
            os.environ.pop("CODING_TEAM_MAIN_ROOT", None)
        else:
            os.environ["CODING_TEAM_MAIN_ROOT"] = old

    facts = {
        "seam_in_run_env": run_env.get("CODING_TEAM_MAIN_ROOT"),
        "ambient_seam_present": "CODING_TEAM_MAIN_ROOT" in os.environ,
        "repo": str(repo),
        "plan_exists": plan.exists(),
        "git_rev_parse_rc": gitr.returncode,
        "git_rev_parse_out": gitr.stdout.strip(),
        "git_rev_parse_err": gitr.stderr.strip()[:200],
        "_git_main_root_inproc": str(gmr),
        "find_active_plan_inproc": str(fap),
        "subprocess_stdout": proc.stdout.strip()[:400],
        "subprocess_stderr": proc.stderr.strip()[:400],
        "python": sys.version.split()[0],
    }
    # Fail on purpose so the message surfaces in --tb=short.
    assert False, "CI_DIAG " + json.dumps(facts, indent=2)
