#!/usr/bin/env python3
"""SessionStart hook: verify skill symlinks are intact.

Scans skill directories in the coding-team repo and checks each has a
corresponding symlink at ~/.claude/skills/<name>. Broken or missing
symlinks mean skills are registered but not accessible.

Advisory only — does not block the session.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from _lib.output import advisory
from _lib.suppression import mark_clean

SUPPRESSION_KEY = "symlink_check_last_clean"

REPO_SKILLS_DIR = Path(__file__).parent.parent / "skills"
CLAUDE_SKILLS_DIR = Path.home() / ".claude" / "skills"


def check_symlinks() -> list[str]:
    """Check that each skill directory in the repo has a valid symlink.

    Returns a list of problem descriptions.
    """
    problems = []

    if not REPO_SKILLS_DIR.is_dir():
        return problems

    for skill_dir in sorted(REPO_SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        if skill_dir.name.startswith((".", "_")):
            continue

        symlink_path = CLAUDE_SKILLS_DIR / skill_dir.name

        if not symlink_path.exists() and not symlink_path.is_symlink():
            problems.append(f"Missing: {skill_dir.name} — no symlink at {symlink_path}")
        elif symlink_path.is_symlink():
            target = symlink_path.resolve()
            if not target.exists():
                problems.append(f"Broken: {skill_dir.name} — symlink points to non-existent {target}")
            elif target != skill_dir.resolve():
                # Symlink exists but points somewhere else — may be intentional
                pass
        # If it exists as a regular directory, that's fine too

    return problems


def main():
    problems = check_symlinks()
    if not problems:
        mark_clean(SUPPRESSION_KEY)
        return  # All symlinks healthy — silent success

    msg = (
        f"Symlink integrity: {len(problems)} issue(s) found.\n"
        + "\n".join(f"  - {p}" for p in problems)
        + "\n\nFix with: ln -sf <repo-skill-dir> ~/.claude/skills/<name>"
    )
    advisory(msg)


if __name__ == "__main__":
    main()
