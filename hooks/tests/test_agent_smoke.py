"""Tier 1 — Agent smoke tests: structural validation for all agent .md files.

NO LLM calls. Pure structural/static analysis via real file reads.
"""

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
AGENTS_DIR = REPO_ROOT / "agents"

VALID_MODELS = {"opus", "sonnet", "haiku"}

KNOWN_TOOLS = {"Read", "Edit", "Write", "Bash", "Glob", "Grep", "LSP", "Agent"}

READ_ONLY_AGENTS = {
    "ct-simplify-auditor",
    "ct-harden-auditor",
    "ct-spec-reviewer",
    "ct-spec-doc-reviewer",
    "ct-plan-doc-reviewer",
    "ct-prompt-craft-auditor",
    "ct-qa-reviewer",
}

WRITE_TOOLS = {"Edit", "Write"}

MAX_LINES = 250

# Matches standalone TODO/FIXME markers: comment-style (# TODO, // TODO) or
# colon-style (TODO:, FIXME:) but not the word embedded in prose like
# "check for TODOs" or table cells mentioning "TODOs, placeholders".
_TODO_PATTERN = re.compile(r"(?:#|//)\s*(?:TODO|FIXME)\b|(?:TODO|FIXME):")


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split an agent file into YAML frontmatter dict and body text.

    Returns (frontmatter_dict, body_text). Raises ValueError if no frontmatter found.
    """
    if not text.startswith("---"):
        raise ValueError("File does not start with YAML frontmatter delimiter")
    end_idx = text.index("---", 3)
    raw_yaml = text[3:end_idx].strip()
    frontmatter = yaml.safe_load(raw_yaml)
    body = text[end_idx + 3:].strip()
    return frontmatter, body


def _agent_stem(path: Path) -> str:
    """Return the stem of an agent file (e.g. 'ct-implementer')."""
    return path.stem


def _collect_agent_files() -> list[Path]:
    """Collect all agent .md files that have YAML frontmatter."""
    agents = []
    for p in sorted(AGENTS_DIR.glob("*.md")):
        content = p.read_text()
        if content.startswith("---"):
            agents.append(p)
    return agents


AGENT_FILES = _collect_agent_files()
AGENT_IDS = [_agent_stem(p) for p in AGENT_FILES]


@pytest.fixture
def agent_files() -> list[Path]:
    """Return all agent .md paths with frontmatter."""
    return AGENT_FILES


# ---------------------------------------------------------------------------
# Frontmatter validation
# ---------------------------------------------------------------------------


@pytest.mark.smoke
@pytest.mark.parametrize("agent_path", AGENT_FILES, ids=AGENT_IDS)
class TestFrontmatter:
    """Validate YAML frontmatter for every agent file."""

    def test_frontmatter_parseable(self, agent_path: Path):
        text = agent_path.read_text()
        fm, _ = _parse_frontmatter(text)
        assert isinstance(fm, dict), "Frontmatter must be a YAML mapping"

    def test_required_fields_present(self, agent_path: Path):
        fm, _ = _parse_frontmatter(agent_path.read_text())
        for field in ("name", "description", "model"):
            assert field in fm, f"Missing required field: {field}"

    def test_model_is_valid_tier(self, agent_path: Path):
        fm, _ = _parse_frontmatter(agent_path.read_text())
        assert fm["model"] in VALID_MODELS, (
            f"Invalid model '{fm['model']}' — must be one of {VALID_MODELS}"
        )

    def test_tools_list_exists(self, agent_path: Path):
        fm, _ = _parse_frontmatter(agent_path.read_text())
        assert "tools" in fm, "Missing 'tools' list"
        assert isinstance(fm["tools"], list), "'tools' must be a list"
        assert len(fm["tools"]) > 0, "'tools' list must not be empty"

    def test_tools_are_known(self, agent_path: Path):
        fm, _ = _parse_frontmatter(agent_path.read_text())
        for tool in fm.get("tools", []):
            is_known = tool in KNOWN_TOOLS or tool.startswith("mcp__")
            assert is_known, f"Unknown tool '{tool}' — must be a known tool or start with 'mcp__'"

    def test_description_length(self, agent_path: Path):
        fm, _ = _parse_frontmatter(agent_path.read_text())
        desc = fm.get("description", "")
        assert len(desc) > 0, "Description must not be empty"
        assert len(desc) <= 300, f"Description is {len(desc)} chars — max 300"


# ---------------------------------------------------------------------------
# Structural validation
# ---------------------------------------------------------------------------


@pytest.mark.smoke
@pytest.mark.parametrize("agent_path", AGENT_FILES, ids=AGENT_IDS)
class TestStructure:
    """Validate body structure for every agent file."""

    def test_has_identity_block(self, agent_path: Path):
        _, body = _parse_frontmatter(agent_path.read_text())
        first_30_lines = "\n".join(body.splitlines()[:30])
        assert "You are" in first_30_lines, (
            "Agent must have an identity block ('You are') in first 30 lines of body"
        )

    def test_pipeline_isolation(self, agent_path: Path):
        stem = _agent_stem(agent_path)
        if not stem.startswith("ct-"):
            pytest.skip("Not a ct-* agent")
        text = agent_path.read_text()
        assert "Do NOT invoke" in text or "Do not invoke" in text, (
            "ct-* agents must have a pipeline isolation block ('Do NOT invoke')"
        )

    def test_read_only_auditors_no_write_tools(self, agent_path: Path):
        stem = _agent_stem(agent_path)
        if stem not in READ_ONLY_AGENTS:
            pytest.skip("Not a read-only auditor")
        fm, _ = _parse_frontmatter(agent_path.read_text())
        tools = set(fm.get("tools", []))
        forbidden = tools & WRITE_TOOLS
        assert not forbidden, (
            f"Read-only auditor '{stem}' must not have write tools: {forbidden}"
        )

    def test_under_line_limit(self, agent_path: Path):
        lines = agent_path.read_text().splitlines()
        assert len(lines) <= MAX_LINES, (
            f"Agent file is {len(lines)} lines — max {MAX_LINES}"
        )

    def test_no_todo_or_fixme(self, agent_path: Path):
        text = agent_path.read_text()
        matches = _TODO_PATTERN.findall(text)
        assert not matches, (
            f"Found TODO/FIXME marker(s) in {agent_path.name}: {matches}"
        )


# ---------------------------------------------------------------------------
# Cross-agent consistency
# ---------------------------------------------------------------------------


@pytest.mark.smoke
class TestCrossAgent:
    """Validate consistency across all agent files."""

    def test_no_duplicate_names(self, agent_files: list[Path]):
        names: dict[str, Path] = {}
        for path in agent_files:
            fm, _ = _parse_frontmatter(path.read_text())
            name = fm["name"]
            assert name not in names, (
                f"Duplicate name '{name}' in {path.name} and {names[name].name}"
            )
            names[name] = path

    def test_ct_agents_reference_coding_team(self, agent_files: list[Path]):
        for path in agent_files:
            stem = _agent_stem(path)
            if not stem.startswith("ct-"):
                continue
            text = path.read_text()
            assert "coding-team" in text.lower() or "coding team" in text.lower(), (
                f"ct-* agent '{stem}' must reference the coding-team pipeline"
            )

    def test_bt_agents_reference_business_team(self, agent_files: list[Path]):
        for path in agent_files:
            stem = _agent_stem(path)
            if not stem.startswith("bt-"):
                continue
            text = path.read_text()
            has_ref = (
                "business-team" in text.lower()
                or "business team" in text.lower()
                or "standalone" in text.lower()
            )
            assert has_ref, (
                f"bt-* agent '{stem}' must reference business-team pipeline or be standalone"
            )
