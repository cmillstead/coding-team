"""Tests for deny-list-audit.py hook."""

import importlib.util
import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

HOOKS_DIR = Path("/Users/cevin/.claude/skills/coding-team/hooks")


def _load_module():
    """Load deny-list-audit.py as a module."""
    spec = importlib.util.spec_from_file_location(
        "deny_list_audit", HOOKS_DIR / "deny-list-audit.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load_module()
check_deny_coverage = mod.check_deny_coverage
REQUIRED_DENY_PATTERNS = mod.REQUIRED_DENY_PATTERNS


def _run_hook_with_settings(settings_content: str | None) -> dict | None:
    """Run deny-list-audit.py as a subprocess with a real temp settings file.

    If settings_content is None, points SETTINGS_PATH at a nonexistent file.
    Returns parsed JSON output or None.
    """
    # Create a wrapper script that overrides SETTINGS_PATH before calling main()
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False
    ) as wrapper:
        if settings_content is not None:
            # Write real settings file
            settings_fd, settings_path = tempfile.mkstemp(suffix=".json")
            with os.fdopen(settings_fd, "w") as sf:
                sf.write(settings_content)
        else:
            settings_path = "/nonexistent/path/settings.json"

        wrapper.write(f"""
import sys, os
sys.path.insert(0, {str(HOOKS_DIR)!r})
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "deny_list_audit", {str(HOOKS_DIR / "deny-list-audit.py")!r}
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod.SETTINGS_PATH = Path({settings_path!r})
mod.main()
""")
        wrapper_path = wrapper.name

    try:
        result = subprocess.run(
            ["python3", wrapper_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.stdout.strip():
            return json.loads(result.stdout)
        return None
    finally:
        os.unlink(wrapper_path)
        if settings_content is not None:
            os.unlink(settings_path)


# --- Unit tests for check_deny_coverage ---


def test_all_patterns_covered_no_output():
    """When deny list covers all required patterns, no missing reported."""
    deny_list = [
        "Edit(~/.ssh/**)",
        "Read(~/.aws/**)",
        "Edit(~/.config/gcloud/**)",
        "Read(~/.kube/**)",
        "Edit(~/.azure/**)",
        "Read(~/Library/Keychains/**)",
        "Edit(~/.password-store/**)",
        "Read(~/.gnupg/**)",
    ]
    missing = check_deny_coverage(deny_list)
    assert missing == []


def test_missing_ssh_reported():
    """If ~/.ssh is not in deny list, it is reported as missing."""
    deny_list = [
        "Edit(~/.aws/**)",
        "Read(~/.config/gcloud/**)",
        "Edit(~/.kube/**)",
        "Read(~/.azure/**)",
        "Edit(~/Library/Keychains/**)",
        "Read(~/.password-store/**)",
        "Edit(~/.gnupg/**)",
    ]
    missing = check_deny_coverage(deny_list)
    assert missing == ["~/.ssh"]


def test_missing_multiple_reported():
    """Multiple missing patterns are all reported."""
    deny_list = [
        "Edit(~/.aws/**)",
        "Read(~/.config/gcloud/**)",
    ]
    missing = check_deny_coverage(deny_list)
    # Should include everything except .aws and .config/gcloud
    assert "~/.ssh" in missing
    assert "~/.kube" in missing
    assert "~/.azure" in missing
    assert "~/Library/Keychains" in missing
    assert "~/.password-store" in missing
    assert "~/.gnupg" in missing
    # These should NOT be in missing
    assert "~/.aws" not in missing
    assert "~/.config/gcloud" not in missing


def test_empty_deny_list_triggers_warning():
    """Empty deny list triggers full warning with all patterns listed."""
    settings = json.dumps({"permissions": {"deny": []}})
    output = _run_hook_with_settings(settings)
    assert output is not None
    assert output["decision"] == "allow"
    assert "EMPTY" in output["reason"]
    for pattern in REQUIRED_DENY_PATTERNS:
        assert pattern in output["reason"]


def test_settings_file_missing_no_crash():
    """If settings.json doesn't exist, graceful handling — no crash."""
    output = _run_hook_with_settings(None)
    assert output is not None
    assert output["decision"] == "allow"
    assert "EMPTY" in output["reason"]


def test_partial_coverage():
    """Some patterns present, some missing — only missing ones reported."""
    deny_list = [
        "Edit(~/.ssh/**)",
        "Read(~/.ssh/**)",
        "Edit(~/.gnupg/**)",
        "Read(~/.gnupg/**)",
    ]
    settings = json.dumps({"permissions": {"deny": deny_list}})
    output = _run_hook_with_settings(settings)
    assert output is not None
    assert output["decision"] == "allow"
    # .ssh and .gnupg are covered, so should NOT appear
    assert "~/.ssh" not in output["reason"]
    assert "~/.gnupg" not in output["reason"]
    # These should appear as missing
    assert "~/.aws" in output["reason"]
    assert "~/.kube" in output["reason"]
    assert "gaps" in output["reason"].lower()
