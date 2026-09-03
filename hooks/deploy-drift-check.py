#!/usr/bin/env python3
"""Claude Code SessionStart hook: detect source↔deployed hook drift.

Compares every *.py file in the source hooks/ and hooks/_lib/ directories
against their deployed counterparts in ~/.claude/hooks/. Reports any files
that are missing in the deployed copy or whose bytes differ.

Never blocks — exits 0 regardless of findings (advisory hook).
Runs once per session via a /tmp marker file.
"""
import sys
from pathlib import Path

SOURCE = Path.home() / ".claude/skills/coding-team/hooks"
DEPLOYED = Path.home() / ".claude/hooks"
MARKER_FILE = Path("/tmp/deploy-drift-checked")

# Hooks that run LIVE from the source dir and are intentionally NOT deployed into
# ~/.claude/hooks/. A missing deployed copy for these is BY DESIGN, not drift — deploying
# them (via deploy.sh) would break their run-from-source contract. Real content drift for
# any OTHER file is still flagged.
SOURCE_ONLY_HOOKS = frozenset({
    "clean-tree-gate.py",
    "engram-pretool-inject.py",
    "engram-session-start.py",
})


def find_drift(source_dir: Path, deployed_dir: Path) -> list[str]:
    """Return sorted relative paths of *.py files under source_dir whose
    deployed counterpart is missing or differs. Includes the _lib/ subdir.
    Only files that exist in source are checked (deployed-only files are ignored)."""
    drifted: list[str] = []

    # Check top-level *.py files
    try:
        for src_file in source_dir.glob("*.py"):
            rel = src_file.name
            deployed_file = deployed_dir / rel
            if not deployed_file.exists():
                # Source-only-by-design hooks have no deployed copy — skip the missing flag.
                if rel not in SOURCE_ONLY_HOOKS:
                    drifted.append(rel)
            else:
                try:
                    if src_file.read_bytes() != deployed_file.read_bytes():
                        drifted.append(rel)
                except OSError:
                    drifted.append(rel)
    except OSError:
        pass

    # Check _lib/*.py files
    src_lib = source_dir / "_lib"
    dep_lib = deployed_dir / "_lib"
    try:
        for src_file in src_lib.glob("*.py"):
            rel = f"_lib/{src_file.name}"
            deployed_file = dep_lib / src_file.name
            if not deployed_file.exists():
                drifted.append(rel)
            else:
                try:
                    if src_file.read_bytes() != deployed_file.read_bytes():
                        drifted.append(rel)
                except OSError:
                    drifted.append(rel)
    except OSError:
        pass

    return sorted(drifted)


def find_stdlib_collisions(source_dir: Path) -> list[str]:
    """Return sorted relative paths of *.py files under source_dir (and its
    _lib/ subdir) whose stem collides with a Python stdlib module name. A hook
    named after a stdlib module (e.g. operator.py) shadows that module and
    crashes every hook in the directory on import. Advisory only — never raises."""
    collisions: list[str] = []
    stdlib_names = sys.stdlib_module_names
    try:
        for src_file in source_dir.glob("*.py"):
            if src_file.stem in stdlib_names:
                collisions.append(src_file.name)
    except OSError:
        pass  # advisory hook: skip an unreadable source dir, never block session start
    try:
        for src_file in (source_dir / "_lib").glob("*.py"):
            if src_file.stem in stdlib_names:
                collisions.append(f"_lib/{src_file.name}")
    except OSError:
        pass  # advisory hook: skip an unreadable _lib dir, never block session start
    return sorted(collisions)


def main() -> None:
    if MARKER_FILE.exists():
        return

    try:
        MARKER_FILE.touch()
    except OSError:
        pass

    if not SOURCE.is_dir():
        return

    try:
        drifted = find_drift(SOURCE, DEPLOYED)
    except OSError:
        drifted = []  # advisory: drift check failed; still run the collision scan

    if drifted:
        file_list = "\n".join(f"  - {f}" for f in drifted)
        print(
            f"⚠️  DEPLOY DRIFT: {len(drifted)} hook file(s) differ between source and deployed copies:\n"
            f"{file_list}\n"
            f"Run `bash ~/.claude/skills/coding-team/scripts/deploy.sh` to sync (source is canonical)."
        )

    collisions = find_stdlib_collisions(SOURCE)
    if collisions:
        collision_list = "\n".join(f"  - {c}" for c in collisions)
        print(
            f"⚠️  STDLIB COLLISION: {len(collisions)} hook file(s) are named after a "
            f"Python stdlib module:\n"
            f"{collision_list}\n"
            f"A hook whose name shadows a stdlib module crashes every hook in its "
            f"directory on import. Rename to a descriptive hyphenated name (e.g. "
            f"`operator-guard.py`) — a hyphen cannot appear in a stdlib module name."
        )


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 — intentional fail-open; advisory hook must never break session start
        pass
    sys.exit(0)
