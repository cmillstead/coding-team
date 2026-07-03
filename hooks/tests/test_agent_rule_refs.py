"""Tests for agent rule-file and reference-file references in agents/ct-*.md.

Verifies that every `~/.claude/rules/<name>.md` reference in an agent
instruction file points to a rule that actually exists in the repo's
rules/ source (and will therefore be deployed to ~/.claude/rules/ by
deploy.sh), and that no agent still uses the old relative `rules/<name>.md`
form, which does not resolve when the agent runs in an arbitrary target
repo.

Also guards the same convention for `agents/reference/...` and
`skills/.../SKILL.md` references: unlike rules/, these files are NOT
deployed standalone by deploy.sh (only agents/ct-*.md and rules/ are), so
their absolute form is the repo location `~/.claude/skills/coding-team/...`,
not `~/.claude/agents/...` or `~/.claude/rules/...`.
"""

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]  # tests/ -> hooks/ -> repo root
AGENTS_DIR = REPO_ROOT / "agents"
RULES_DIR = REPO_ROOT / "rules"

ABSOLUTE_RULE_REF = re.compile(r"~/\.claude/rules/([\w-]+)\.md")
RELATIVE_RULE_REF = re.compile(r"`rules/([\w-]+)\.md`")
RELATIVE_REFERENCE_REF = re.compile(r"`(agents/reference/[\w.-]+\.md)`")
RELATIVE_SKILL_REF = re.compile(r"`(skills/[\w./-]+/SKILL\.md)`")


class TestAgentRuleRefs:
    def test_every_absolute_rule_ref_has_a_deployable_source(self):
        """Every `~/.claude/rules/<name>.md` reference in an agent file must
        correspond to a real `rules/<name>.md` source file that deploy.sh
        actually deploys — otherwise the path the agent is told to read
        never gets populated.

        README.md is excluded: deploy.sh's rules/ loop (scripts/deploy.sh,
        ~line 82-85) explicitly skips it as deploy meta-doc, not a
        behavioral rule, so a reference to it would exist as a source file
        but never land at ~/.claude/rules/README.md.
        """
        missing = []
        for agent_file in sorted(AGENTS_DIR.glob("ct-*.md")):
            text = agent_file.read_text()
            for name in ABSOLUTE_RULE_REF.findall(text):
                if name == "README":
                    missing.append(
                        f"{agent_file.name} references README.md, but deploy.sh skips "
                        "rules/README.md (deploy meta-doc) — it never deploys"
                    )
                    continue
                source = RULES_DIR / f"{name}.md"
                if not source.exists():
                    missing.append(f"{agent_file.name} references {name}.md, but {source} does not exist")

        assert not missing, "\n".join(missing)

    def test_no_agent_uses_relative_rule_path(self):
        """No agent file may reference a rule via the old backticked
        relative form `rules/<name>.md` — it does not resolve when the
        agent runs in an arbitrary target repo. References must use the
        deployed absolute path `~/.claude/rules/<name>.md` instead."""
        offenders = []
        for agent_file in sorted(AGENTS_DIR.glob("ct-*.md")):
            text = agent_file.read_text()
            for name in RELATIVE_RULE_REF.findall(text):
                offenders.append(f"{agent_file.name} still references relative `rules/{name}.md`")

        assert not offenders, "\n".join(offenders)

    def test_no_agent_uses_relative_reference_or_skill_path(self):
        """No agent file may reference `agents/reference/...` or
        `skills/.../SKILL.md` via a backticked relative path — like
        rules/<name>.md, these do not resolve when the agent runs in an
        arbitrary target repo. Unlike rules/, agents/reference/ and
        skills/ are NOT deployed standalone by deploy.sh, so references
        must use the repo-absolute form
        `~/.claude/skills/coding-team/agents/reference/...` or
        `~/.claude/skills/coding-team/skills/.../SKILL.md` instead."""
        offenders = []
        for agent_file in sorted(AGENTS_DIR.glob("ct-*.md")):
            text = agent_file.read_text()
            for ref in RELATIVE_REFERENCE_REF.findall(text):
                offenders.append(f"{agent_file.name} still references relative `{ref}`")
            for ref in RELATIVE_SKILL_REF.findall(text):
                offenders.append(f"{agent_file.name} still references relative `{ref}`")

        assert not offenders, "\n".join(offenders)

    def test_at_least_one_absolute_rule_ref_found(self):
        """Sanity check: the scan itself must find references, otherwise
        the two assertions above would trivially pass on an empty match."""
        found = []
        for agent_file in sorted(AGENTS_DIR.glob("ct-*.md")):
            text = agent_file.read_text()
            found.extend(ABSOLUTE_RULE_REF.findall(text))

        assert found, "expected at least one ~/.claude/rules/<name>.md reference in agents/ct-*.md"
