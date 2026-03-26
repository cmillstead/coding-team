"""Tier 2 — Skill eval tests: structural validation and eval framework for SKILL.md files.

Smoke tests (tiers 1-3) validate frontmatter, structure, and cross-skill consistency.
Eval harness (tier 4) is gated behind @pytest.mark.llm_eval — skipped by default.
"""

import re
import subprocess
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
ROOT_SKILL = REPO_ROOT / "SKILL.md"

# Context saturation threshold from CLAUDE.md
MAX_SKILL_LINES = 200
MAX_DESCRIPTION_CHARS = 500

# Trigger phrase patterns — description should start with one of these
TRIGGER_PATTERNS = re.compile(
    r"^(Use when|Use before|Use after|When |Push |Write |Remove |Restrict |WCAG |Per-feature |\w+ing |\w+ when |\w+ and |\w+ or )",
    re.IGNORECASE,
)


def _collect_skill_files() -> list[Path]:
    """Collect all SKILL.md files (sub-skills + root)."""
    skills = sorted(SKILLS_DIR.glob("*/SKILL.md"))
    if ROOT_SKILL.exists():
        skills.append(ROOT_SKILL)
    return skills


def _parse_frontmatter(path: Path) -> dict:
    """Parse YAML frontmatter from a SKILL.md file."""
    text = path.read_text()
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        return yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}


def _skill_id(path: Path) -> str:
    """Return a human-readable test ID for a skill path."""
    if path == ROOT_SKILL:
        return "coding-team"
    return path.parent.name


SKILL_FILES = _collect_skill_files()
SKILL_IDS = [_skill_id(p) for p in SKILL_FILES]


# ---------------------------------------------------------------------------
# Tier 1: Frontmatter validation
# ---------------------------------------------------------------------------

class TestFrontmatterValidation:
    """Validate YAML frontmatter for every skill."""

    @pytest.mark.smoke
    @pytest.mark.parametrize("skill_path", SKILL_FILES, ids=SKILL_IDS)
    def test_frontmatter_is_parseable(self, skill_path: Path):
        fm = _parse_frontmatter(skill_path)
        assert fm, f"{skill_path} has no parseable YAML frontmatter"

    @pytest.mark.smoke
    @pytest.mark.parametrize("skill_path", SKILL_FILES, ids=SKILL_IDS)
    def test_required_fields_present(self, skill_path: Path):
        fm = _parse_frontmatter(skill_path)
        assert "name" in fm, f"{skill_path} missing required field: name"
        assert "description" in fm, f"{skill_path} missing required field: description"

    @pytest.mark.smoke
    @pytest.mark.parametrize("skill_path", SKILL_FILES, ids=SKILL_IDS)
    def test_description_starts_with_trigger_phrase(self, skill_path: Path):
        fm = _parse_frontmatter(skill_path)
        desc = fm.get("description", "")
        assert TRIGGER_PATTERNS.match(desc), (
            f"{_skill_id(skill_path)}: description does not start with a trigger phrase. "
            f"Got: {desc[:80]!r}"
        )

    @pytest.mark.smoke
    @pytest.mark.parametrize("skill_path", SKILL_FILES, ids=SKILL_IDS)
    def test_name_matches_directory(self, skill_path: Path):
        fm = _parse_frontmatter(skill_path)
        expected_name = _skill_id(skill_path)
        assert fm.get("name") == expected_name, (
            f"Frontmatter name {fm.get('name')!r} does not match directory {expected_name!r}"
        )


# ---------------------------------------------------------------------------
# Tier 2: Structural validation
# ---------------------------------------------------------------------------

class TestStructuralValidation:
    """Validate structure and content quality for every skill."""

    @pytest.mark.smoke
    @pytest.mark.parametrize("skill_path", SKILL_FILES, ids=SKILL_IDS)
    def test_under_line_limit(self, skill_path: Path):
        line_count = len(skill_path.read_text().splitlines())
        assert line_count <= MAX_SKILL_LINES, (
            f"{_skill_id(skill_path)}: {line_count} lines exceeds {MAX_SKILL_LINES} limit"
        )

    @pytest.mark.smoke
    @pytest.mark.parametrize("skill_path", SKILL_FILES, ids=SKILL_IDS)
    def test_has_routing_guidance(self, skill_path: Path):
        text = skill_path.read_text().lower()
        routing_patterns = [
            "when to use",
            "when not to use",
            "do not use",
            "use instead",
            "use when",
            "do not use for",
            "for ",  # "For X, use /other-skill" routing in descriptions
        ]
        has_routing = any(pattern in text for pattern in routing_patterns)
        assert has_routing, (
            f"{_skill_id(skill_path)}: no routing guidance found "
            f"(expected 'When to Use', 'When NOT to Use', or equivalent)"
        )

    @pytest.mark.smoke
    @pytest.mark.parametrize("skill_path", SKILL_FILES, ids=SKILL_IDS)
    def test_no_todo_or_fixme(self, skill_path: Path):
        text = skill_path.read_text()
        for marker in ("TODO", "FIXME"):
            # Word boundary match — "TODOs" (plural noun) is not a TODO marker
            if re.search(rf"\b{marker}\b(?!s\b)", text):
                pytest.fail(f"{_skill_id(skill_path)}: contains {marker} marker")

    @pytest.mark.smoke
    @pytest.mark.parametrize("skill_path", SKILL_FILES, ids=SKILL_IDS)
    def test_description_under_char_limit(self, skill_path: Path):
        fm = _parse_frontmatter(skill_path)
        desc = fm.get("description", "")
        assert len(desc) <= MAX_DESCRIPTION_CHARS, (
            f"{_skill_id(skill_path)}: description is {len(desc)} chars, "
            f"exceeds {MAX_DESCRIPTION_CHARS} limit"
        )


# ---------------------------------------------------------------------------
# Tier 3: Cross-skill consistency
# ---------------------------------------------------------------------------

class TestCrossSkillConsistency:
    """Validate consistency across all skills."""

    @pytest.mark.smoke
    def test_no_duplicate_names(self):
        names: dict[str, Path] = {}
        for skill_path in SKILL_FILES:
            fm = _parse_frontmatter(skill_path)
            name = fm.get("name", "")
            if name in names:
                pytest.fail(
                    f"Duplicate skill name {name!r}: "
                    f"{names[name]} and {skill_path}"
                )
            names[name] = skill_path

    @pytest.mark.smoke
    def test_cross_references_resolve(self):
        """Skills that reference other skills via /name should point to existing dirs.

        Only checks explicit skill invocation patterns in frontmatter descriptions:
        'use /skill-name', '(/skill-name)', or standalone '/skill-name' references.
        Ignores path fragments in code blocks and general prose.
        """
        # Match /name only in description context — preceded by "use ", "(", or start-of-word
        skill_ref_pattern = re.compile(r"(?:use |, use |\()(/[\w-]+)\b")
        known_skills = {p.parent.name for p in SKILLS_DIR.glob("*/SKILL.md")}
        known_skills.add("coding-team")

        # External skills referenced but not part of this repo
        external_skills = {
            "/prompt-engineer", "/design-review", "/review",
            "/agency-testing-accessibility-auditor",
            "/brainstorming", "/scan-code", "/scan-security",
            "/scan-product", "/scan-adversarial",
            "/ship", "/freeze", "/unfreeze", "/retro",
        }

        broken_refs: list[str] = []
        for skill_path in SKILL_FILES:
            fm = _parse_frontmatter(skill_path)
            desc = fm.get("description", "")
            skill_name = _skill_id(skill_path)
            refs = skill_ref_pattern.findall(desc)
            for ref in refs:
                bare_name = ref.lstrip("/")
                if bare_name in known_skills:
                    continue
                if ref in external_skills:
                    continue
                broken_refs.append(
                    f"{skill_name} description references {ref} — "
                    f"not found in skills/ or external_skills allowlist"
                )

        if broken_refs:
            pytest.fail(
                f"Broken cross-references:\n" + "\n".join(broken_refs)
            )


# ---------------------------------------------------------------------------
# Tier 4: Eval harness (LLM-gated, skipped by default)
# ---------------------------------------------------------------------------

SKILL_EVAL_CASES = {
    "coding-team": [
        {
            "prompt": "I need to add a new authentication feature to the API",
            "expected_skill": "coding-team",
            "not_expected": ["debug", "release", "doc-write"],
        },
        {
            "prompt": "Refactor the database layer to use connection pooling",
            "expected_skill": "coding-team",
            "not_expected": ["dep-audit", "incident"],
        },
    ],
    "release": [
        {
            "prompt": "Ship this branch, create a PR and merge it",
            "expected_skill": "release",
            "not_expected": ["debug", "coding-team"],
        },
    ],
    "debug": [
        {
            "prompt": "The tests are failing with a TypeError on line 42",
            "expected_skill": "debug",
            "not_expected": ["release", "doc-write"],
        },
        {
            "prompt": "Something is broken in production, investigate the root cause",
            "expected_skill": "debug",
            "not_expected": ["release", "onboard"],
        },
    ],
    "prompt-craft": [
        {
            "prompt": "Claude Code keeps ignoring my instructions about testing",
            "expected_skill": "prompt-craft",
            "not_expected": ["debug", "coding-team"],
        },
    ],
    "verify": [
        {
            "prompt": "Verify that the tests actually pass before we merge",
            "expected_skill": "verify",
            "not_expected": ["release", "debug"],
        },
    ],
}


def _flatten_eval_cases() -> list[tuple[str, dict]]:
    """Flatten SKILL_EVAL_CASES into (case_id, case_dict) tuples for parametrize."""
    cases = []
    for skill_name, skill_cases in SKILL_EVAL_CASES.items():
        for idx, case in enumerate(skill_cases):
            case_id = f"{skill_name}-{idx}"
            cases.append((case_id, case))
    return cases


EVAL_CASES = _flatten_eval_cases()
EVAL_IDS = [case_id for case_id, _ in EVAL_CASES]


@pytest.mark.llm_eval
class TestSkillEvalHarness:
    """LLM-based skill routing evaluation.

    Gated behind @pytest.mark.llm_eval — skipped unless explicitly requested:
        pytest -m llm_eval hooks/tests/test_skill_evals.py
    """

    @pytest.mark.parametrize("case_id,case", EVAL_CASES, ids=EVAL_IDS)
    def test_skill_routing(self, case_id: str, case: dict):
        """Invoke claude with --max-turns 0 and verify skill routing."""
        prompt = case["prompt"]
        expected = case["expected_skill"]
        not_expected = case["not_expected"]

        result = subprocess.run(
            ["claude", "-p", prompt, "--max-turns", "0"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        response = result.stdout.lower()

        assert expected.lower() in response, (
            f"Expected skill {expected!r} not mentioned in response for: {prompt!r}"
        )

        for blocked in not_expected:
            # Check for explicit skill invocation patterns, not just substring
            skill_pattern = re.compile(rf"/{blocked}\b", re.IGNORECASE)
            assert not skill_pattern.search(response), (
                f"Unexpected skill /{blocked} mentioned in response for: {prompt!r}"
            )
