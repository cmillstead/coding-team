"""Tests for deploy-drift-check.py hook — driving find_drift directly with tmp_path."""

import importlib.util
import sys
from pathlib import Path


HOOKS_DIR = Path("/Users/cevin/.claude/skills/coding-team/hooks")


def _load_find_drift():
    """Import find_drift from deploy-drift-check.py via importlib."""
    spec = importlib.util.spec_from_file_location(
        "deploy_drift_check",
        HOOKS_DIR / "deploy-drift-check.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.find_drift


find_drift = _load_find_drift()


class TestNoDrift:
    def test_identical_files_return_empty(self, tmp_path):
        """No drift: source and deployed have identical output.py and _lib/event.py."""
        # Arrange
        src = tmp_path / "source" / "hooks"
        dep = tmp_path / "deployed" / "hooks"
        src_lib = src / "_lib"
        dep_lib = dep / "_lib"
        for d in (src, dep, src_lib, dep_lib):
            d.mkdir(parents=True)

        content = b"# hook content\npass\n"
        (src / "output.py").write_bytes(content)
        (dep / "output.py").write_bytes(content)

        lib_content = b"# lib event\npass\n"
        (src_lib / "event.py").write_bytes(lib_content)
        (dep_lib / "event.py").write_bytes(lib_content)

        # Act
        result = find_drift(src, dep)

        # Assert
        assert result == []


class TestContentDrift:
    def test_differing_bytes_reported(self, tmp_path):
        """Content drift: deployed output.py bytes differ from source → returns ['output.py']."""
        # Arrange
        src = tmp_path / "source" / "hooks"
        dep = tmp_path / "deployed" / "hooks"
        src.mkdir(parents=True)
        dep.mkdir(parents=True)

        (src / "output.py").write_bytes(b"# source version\n")
        (dep / "output.py").write_bytes(b"# deployed differs\n")

        # Act
        result = find_drift(src, dep)

        # Assert
        assert result == ["output.py"]


class TestMissingDeployedFile:
    def test_missing_deployed_file_reported(self, tmp_path):
        """Missing deployed file: source has codesight-hooks.py, deployed doesn't → in result."""
        # Arrange
        src = tmp_path / "source" / "hooks"
        dep = tmp_path / "deployed" / "hooks"
        src.mkdir(parents=True)
        dep.mkdir(parents=True)

        (src / "codesight-hooks.py").write_bytes(b"# hook\n")
        # deployed dir exists but does NOT contain codesight-hooks.py

        # Act
        result = find_drift(src, dep)

        # Assert
        assert "codesight-hooks.py" in result


class TestLibDrift:
    def test_differing_lib_file_reported_with_prefix(self, tmp_path):
        """_lib drift: a differing _lib/foo.py shows up as '_lib/foo.py' in the result."""
        # Arrange
        src = tmp_path / "source" / "hooks"
        dep = tmp_path / "deployed" / "hooks"
        src_lib = src / "_lib"
        dep_lib = dep / "_lib"
        for d in (src, dep, src_lib, dep_lib):
            d.mkdir(parents=True)

        (src_lib / "foo.py").write_bytes(b"# foo source\n")
        (dep_lib / "foo.py").write_bytes(b"# foo deployed differs\n")

        # Act
        result = find_drift(src, dep)

        # Assert
        assert result == ["_lib/foo.py"]


class TestDeployedOnlyFileIgnored:
    def test_deployed_only_file_not_reported(self, tmp_path):
        """Deployed-only file: a file present only in deployed (not source) is NOT reported."""
        # Arrange
        src = tmp_path / "source" / "hooks"
        dep = tmp_path / "deployed" / "hooks"
        src.mkdir(parents=True)
        dep.mkdir(parents=True)

        # deployed has an extra file that source doesn't have
        (dep / "deployed-only.py").write_bytes(b"# exists only in deployed\n")
        # source has nothing

        # Act
        result = find_drift(src, dep)

        # Assert
        assert "deployed-only.py" not in result
        assert result == []
