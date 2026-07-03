#!/usr/bin/env python3
"""Verify coding-team's cross-file indexes stay consistent.

Checks (stdlib only, no third-party deps):
  1. Every agents/*.md (except agents/reference/*) is referenced at least
     once in phases/*.md or SKILL.md.
  2. Every path cited in phases/reference-files.md's tables exists on disk.
  3. No file in phases/, agents/, commands/, skills/, SKILL.md, or README.md
     references any dead artifact from the pre-remediation harness
     (cookbook/phases/, cookbook/references/, prompts/*.md, ct-builder.md,
     ct-reviewer.md, ct-qa.md [word-boundary — must not false-positive on
     ct-qa-reviewer.md], ct-harden-reviewer.md, ct-plan-reviewer.md,
     ct-prompt-reviewer.md) or calls a nonexistent `Teammate(` tool.
  4. Every skills/*/SKILL.md directory appears in phases/reference-files.md's
     skills table.

Exit code 0 = all checks pass. Exit code 1 = at least one legitimate failure.

Two deliberate exceptions are allowlisted below (see ALLOWLIST) — do not add
to this list without a comment explaining why the hit is not a regression.
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# ALLOWLIST — deliberate, documented exceptions to check 3.
#
# Each entry is a (file, pattern-substring) pair. A hit is only suppressed
# if BOTH the file path and the matched dead-reference text match an entry.
# ---------------------------------------------------------------------------
ALLOWLIST = {
    # Documents the Teammate anti-pattern by name, on purpose, so agents know
    # NOT to write it — this is the one place "Teammate(" is expected to
    # appear as prose describing what NOT to do.
    ("skills/prompt-craft/language-rules.md", "Teammate("),
    # Historical artifact describing the old cookbook fork's context
    # inheritance model — kept for archaeology, not a live reference.
    ("cookbook/context-inheritance-matrix.md", "cookbook/phases/"),
    ("cookbook/context-inheritance-matrix.md", "cookbook/references/"),
}

DEAD_REFERENCE_PATTERNS = [
    r"cookbook/phases/",
    r"cookbook/references/",
    r"\bprompts/[A-Za-z0-9_.-]+\.md\b",
    r"\bct-builder\.md\b",
    r"\bct-reviewer\.md\b",
    r"\bct-qa\.md\b",  # word-boundary: must NOT match ct-qa-reviewer.md
    r"\bct-harden-reviewer\.md\b",
    r"\bct-plan-reviewer\.md\b",
    r"\bct-prompt-reviewer\.md\b",
    r"Teammate\(",
]
DEAD_REFERENCE_RE = re.compile("|".join(DEAD_REFERENCE_PATTERNS))

# Directories/files whose content check 3 scans.
CHECK3_TARGET_DIRS = ["phases", "agents", "commands", "skills"]
CHECK3_TARGET_FILES = ["SKILL.md", "README.md"]

failures = []


def fail(check, message):
    failures.append(f"[{check}] {message}")


def iter_md_files(dirs, files):
    seen = set()
    for d in dirs:
        base = REPO_ROOT / d
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.md")):
            if path not in seen:
                seen.add(path)
                yield path
    for f in files:
        path = REPO_ROOT / f
        if path.is_file() and path not in seen:
            seen.add(path)
            yield path


# ---------------------------------------------------------------------------
# Check 1: every agents/*.md (except agents/reference/*) is referenced
# somewhere in phases/*.md or SKILL.md.
# ---------------------------------------------------------------------------
def check1_agents_referenced():
    agents_dir = REPO_ROOT / "agents"
    if not agents_dir.is_dir():
        fail("check1", "agents/ directory does not exist")
        return

    agent_files = sorted(
        p for p in agents_dir.glob("*.md") if p.is_file()
    )  # glob (not rglob) excludes agents/reference/* automatically

    referencing_text = ""
    phases_dir = REPO_ROOT / "phases"
    if phases_dir.is_dir():
        for p in sorted(phases_dir.glob("*.md")):
            referencing_text += p.read_text(encoding="utf-8", errors="replace")
    skill_md = REPO_ROOT / "SKILL.md"
    if skill_md.is_file():
        referencing_text += skill_md.read_text(encoding="utf-8", errors="replace")

    for agent_file in agent_files:
        name = agent_file.name
        if name not in referencing_text:
            fail(
                "check1",
                f"agents/{name} is not referenced in any phases/*.md or SKILL.md",
            )


# ---------------------------------------------------------------------------
# Check 2: every path cited in phases/reference-files.md's tables exists.
# ---------------------------------------------------------------------------
def check2_reference_files_paths_exist():
    ref_file = REPO_ROOT / "phases" / "reference-files.md"
    if not ref_file.is_file():
        fail("check2", "phases/reference-files.md does not exist")
        return

    text = ref_file.read_text(encoding="utf-8", errors="replace")
    # Extract every `path/like/this.md` backtick-quoted token that looks like
    # a repo-relative path (contains a "/" and ends in a known extension).
    candidates = re.findall(r"`([A-Za-z0-9_./-]+\.[A-Za-z0-9]+)`", text)
    checked = set()
    for candidate in candidates:
        if candidate in checked:
            continue
        checked.add(candidate)
        # Skip things that are clearly not repo paths (e.g. "SKILL.md" alone
        # is valid at repo root; anything with a leading slash or "~" is not
        # a repo-relative path we can check here).
        if candidate.startswith("~") or candidate.startswith("/"):
            continue
        target = REPO_ROOT / candidate
        if not target.exists():
            fail(
                "check2",
                f"phases/reference-files.md cites `{candidate}` but it does not exist",
            )


# ---------------------------------------------------------------------------
# Check 3: no live file references dead pre-remediation artifacts.
# ---------------------------------------------------------------------------
def check3_no_dead_references():
    for path in iter_md_files(CHECK3_TARGET_DIRS, CHECK3_TARGET_FILES):
        rel = path.relative_to(REPO_ROOT).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in DEAD_REFERENCE_RE.finditer(text):
            matched_text = match.group(0)
            if _is_allowlisted(rel, matched_text):
                continue
            line_no = text.count("\n", 0, match.start()) + 1
            fail(
                "check3",
                f"{rel}:{line_no} references dead artifact `{matched_text}`",
            )


def _is_allowlisted(rel_path, matched_text):
    for allow_file, allow_pattern in ALLOWLIST:
        if rel_path == allow_file and allow_pattern in matched_text:
            return True
        # Also allow substring containment the other way (matched_text may be
        # a full path like "prompts/foo.md" while allow_pattern is a prefix).
        if rel_path == allow_file and matched_text.startswith(
            allow_pattern.rstrip("(")
        ):
            return True
    return False


# ---------------------------------------------------------------------------
# Check 4: every skills/*/SKILL.md dir appears in reference-files.md's
# skills table.
# ---------------------------------------------------------------------------
def check4_all_skills_indexed():
    ref_file = REPO_ROOT / "phases" / "reference-files.md"
    if not ref_file.is_file():
        fail("check4", "phases/reference-files.md does not exist (needed for check 4)")
        return
    ref_text = ref_file.read_text(encoding="utf-8", errors="replace")

    skills_dir = REPO_ROOT / "skills"
    if not skills_dir.is_dir():
        fail("check4", "skills/ directory does not exist")
        return

    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            continue  # not a real skill dir (e.g. stray non-skill folder)
        expected = f"skills/{skill_dir.name}/SKILL.md"
        if expected not in ref_text:
            fail(
                "check4",
                f"skills/{skill_dir.name}/SKILL.md exists but is not listed in "
                "phases/reference-files.md's skills table",
            )


def main():
    check1_agents_referenced()
    check2_reference_files_paths_exist()
    check3_no_dead_references()
    check4_all_skills_indexed()

    if failures:
        print(f"check-indexes.py: {len(failures)} failure(s)\n")
        for f in failures:
            print(f"  - {f}")
        print()
        sys.exit(1)

    print("check-indexes.py: all checks passed")
    sys.exit(0)


if __name__ == "__main__":
    main()
