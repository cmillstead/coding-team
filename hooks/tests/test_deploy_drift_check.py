"""Tests for deploy-drift-check.py hook — driving find_drift directly with tmp_path."""

import importlib.util
from pathlib import Path


HOOKS_DIR = Path(__file__).resolve().parent.parent  # tests/ -> hooks/


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


def _load_module():
    """Load the whole deploy-drift-check module (for find_stdlib_collisions / main /
    the SOURCE|DEPLOYED|MARKER_FILE attributes). Distinct from _load_find_drift above,
    which returns only the find_drift callable — both coexist, neither redefines the other."""
    spec = importlib.util.spec_from_file_location(
        "deploy_drift_check", HOOKS_DIR / "deploy-drift-check.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_py(directory: Path, name: str) -> None:
    (directory / name).write_text("x = 1\n")


class TestFindStdlibCollisions:
    def test_colliding_top_level_file_flagged(self, tmp_path):
        hook = _load_module()
        _write_py(tmp_path, "operator.py")
        assert hook.find_stdlib_collisions(tmp_path) == ["operator.py"]

    def test_non_colliding_files_not_flagged(self, tmp_path):
        hook = _load_module()
        _write_py(tmp_path, "deploy-drift-check.py")
        _write_py(tmp_path, "ci-orphan-detector.py")
        assert hook.find_stdlib_collisions(tmp_path) == []

    def test_colliding_lib_file_flagged(self, tmp_path):
        hook = _load_module()
        lib = tmp_path / "_lib"
        lib.mkdir()
        _write_py(lib, "types.py")
        assert hook.find_stdlib_collisions(tmp_path) == ["_lib/types.py"]

    def test_mixed_returns_only_collisions_sorted(self, tmp_path):
        hook = _load_module()
        lib = tmp_path / "_lib"
        lib.mkdir()
        _write_py(tmp_path, "operator.py")
        _write_py(tmp_path, "safe_hook.py")
        _write_py(lib, "io.py")
        _write_py(lib, "helpers.py")
        assert hook.find_stdlib_collisions(tmp_path) == ["_lib/io.py", "operator.py"]

    def test_missing_dir_returns_empty_never_raises(self, tmp_path):
        hook = _load_module()
        assert hook.find_stdlib_collisions(tmp_path / "does-not-exist") == []


class TestMainCollisionWarning:
    # mock-ok: pytest monkeypatch below performs real dependency injection of the
    # module-level Path constants (SOURCE/DEPLOYED/MARKER_FILE) — each is swapped for
    # another real Path under tmp_path, no behavior is faked. main() reads these module
    # globals directly, so redirecting them at real temp files requires setattr; the
    # hook's real find_stdlib_collisions/find_drift logic runs unchanged against real files.
    def test_warning_prints_when_collision_present(self, tmp_path, capsys, monkeypatch):  # mock-ok: see class note
        hook = _load_module()
        source = tmp_path / "source"
        source.mkdir()
        _write_py(source, "operator.py")
        monkeypatch.setattr(hook, "SOURCE", source)  # mock-ok: real Path DI
        monkeypatch.setattr(hook, "DEPLOYED", source)  # mock-ok: real Path DI (identical -> no drift noise)
        monkeypatch.setattr(hook, "MARKER_FILE", tmp_path / "marker")  # mock-ok: real Path DI (unique marker)
        hook.main()
        out = capsys.readouterr().out
        assert "STDLIB COLLISION" in out
        assert "operator.py" in out

    def test_no_warning_when_clean(self, tmp_path, capsys, monkeypatch):  # mock-ok: see class note
        hook = _load_module()
        source = tmp_path / "source"
        source.mkdir()
        _write_py(source, "safe-hook.py")
        monkeypatch.setattr(hook, "SOURCE", source)  # mock-ok: real Path DI
        monkeypatch.setattr(hook, "DEPLOYED", source)  # mock-ok: real Path DI
        monkeypatch.setattr(hook, "MARKER_FILE", tmp_path / "marker")  # mock-ok: real Path DI (unique marker)
        hook.main()
        out = capsys.readouterr().out
        assert "STDLIB COLLISION" not in out
