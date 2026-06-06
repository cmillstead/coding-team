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
        return

    if not drifted:
        return

    file_list = "\n".join(f"  - {f}" for f in drifted)
    print(
        f"⚠️  DEPLOY DRIFT: {len(drifted)} hook file(s) differ between source and deployed copies:\n"
        f"{file_list}\n"
        f"Run `bash ~/.claude/skills/coding-team/scripts/deploy.sh` to sync (source is canonical)."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 — intentional fail-open; advisory hook must never break session start
        pass
    sys.exit(0)
