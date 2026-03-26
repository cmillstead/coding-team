"""Tests for plan-completeness-check.py finding number extraction."""

import json
import subprocess
from pathlib import Path

import pytest


HOOKS_DIR = Path("/Users/cevin/.claude/skills/coding-team/hooks")


def run_python_extract(text: str) -> set:
    """Run the extract_finding_numbers function via subprocess and return results."""
    code = (
        f"import sys; sys.path.insert(0, {str(HOOKS_DIR)!r})\n"
        f"import importlib.util, json\n"
        f"spec = importlib.util.spec_from_file_location('pcc', {str(HOOKS_DIR / 'plan-completeness-check.py')!r})\n"
        f"mod = importlib.util.module_from_spec(spec)\n"
        f"spec.loader.exec_module(mod)\n"
        f"print(json.dumps(sorted(mod.extract_finding_numbers({text!r}))))\n"
    )
    result = subprocess.run(
        ["python3", "-c", code],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return set(json.loads(result.stdout))


class TestFindingNumberExtraction:
    def test_extracts_f_numbers(self):
        findings = run_python_extract("F1 F2 F3")
        assert findings == {"1", "2", "3"}

    def test_firefox_does_not_match(self):
        findings = run_python_extract("Firefox")
        assert findings == set()

    def test_mixed_text_with_findings(self):
        findings = run_python_extract("Fix F12 and check F7 results")
        assert "12" in findings
        assert "7" in findings

    def test_no_findings(self):
        findings = run_python_extract("No findings here at all")
        assert findings == set()
