"""Tests for symlink-integrity-check.py hook."""

import importlib.util
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path("/Users/cevin/.claude/skills/coding-team/hooks")


def load_module():
    """Load the hook module via importlib to avoid dash-in-name import issues."""
    spec = importlib.util.spec_from_file_location(
        "symlink_integrity_check",
        HOOKS_DIR / "symlink-integrity-check.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mod():
    """Return a fresh import of the hook module."""
    return load_module()


class TestNoSkillsDir:
    def test_no_skills_dir_no_output(self, mod, tmp_path):
        """When REPO_SKILLS_DIR doesn't exist, no problems are reported."""
        mod.REPO_SKILLS_DIR = tmp_path / "nonexistent"
        problems = mod.check_symlinks()
        assert problems == []


class TestAllSymlinksValid:
    def test_all_symlinks_valid_no_output(self, mod, tmp_path):
        """When all symlinks exist and resolve correctly, no problems are reported."""
        repo_skills = tmp_path / "repo" / "skills"
        claude_skills = tmp_path / "claude" / "skills"
        repo_skills.mkdir(parents=True)
        claude_skills.mkdir(parents=True)

        # Create a skill directory in the repo
        skill_dir = repo_skills / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# My Skill")

        # Create a valid symlink pointing to the repo skill
        symlink = claude_skills / "my-skill"
        symlink.symlink_to(skill_dir)

        mod.REPO_SKILLS_DIR = repo_skills
        mod.CLAUDE_SKILLS_DIR = claude_skills

        problems = mod.check_symlinks()
        assert problems == []


class TestMissingSymlink:
    def test_missing_symlink_reported(self, mod, tmp_path):
        """When a skill dir exists but no symlink, it is reported as missing."""
        repo_skills = tmp_path / "repo" / "skills"
        claude_skills = tmp_path / "claude" / "skills"
        repo_skills.mkdir(parents=True)
        claude_skills.mkdir(parents=True)

        # Create a skill directory in the repo but no symlink
        skill_dir = repo_skills / "orphan-skill"
        skill_dir.mkdir()

        mod.REPO_SKILLS_DIR = repo_skills
        mod.CLAUDE_SKILLS_DIR = claude_skills

        problems = mod.check_symlinks()
        assert len(problems) == 1
        assert "Missing" in problems[0]
        assert "orphan-skill" in problems[0]


class TestBrokenSymlink:
    def test_broken_symlink_reported(self, mod, tmp_path):
        """When symlink exists but target is gone, it is reported as broken."""
        repo_skills = tmp_path / "repo" / "skills"
        claude_skills = tmp_path / "claude" / "skills"
        repo_skills.mkdir(parents=True)
        claude_skills.mkdir(parents=True)

        # Create a skill directory in the repo
        skill_dir = repo_skills / "broken-skill"
        skill_dir.mkdir()

        # Create a symlink pointing to a non-existent target
        dead_target = tmp_path / "dead" / "target"
        symlink = claude_skills / "broken-skill"
        symlink.symlink_to(dead_target)

        mod.REPO_SKILLS_DIR = repo_skills
        mod.CLAUDE_SKILLS_DIR = claude_skills

        problems = mod.check_symlinks()
        assert len(problems) == 1
        assert "Broken" in problems[0]
        assert "broken-skill" in problems[0]


class TestHiddenDirsSkipped:
    def test_hidden_dirs_skipped(self, mod, tmp_path):
        """Directories starting with . or _ are skipped."""
        repo_skills = tmp_path / "repo" / "skills"
        claude_skills = tmp_path / "claude" / "skills"
        repo_skills.mkdir(parents=True)
        claude_skills.mkdir(parents=True)

        # Create hidden/underscore directories — should be ignored
        (repo_skills / ".hidden-skill").mkdir()
        (repo_skills / "_internal").mkdir()

        mod.REPO_SKILLS_DIR = repo_skills
        mod.CLAUDE_SKILLS_DIR = claude_skills

        problems = mod.check_symlinks()
        assert problems == []


class TestRegularDirAccepted:
    def test_regular_dir_accepted(self, mod, tmp_path):
        """A non-symlink directory at the target path is accepted (no error)."""
        repo_skills = tmp_path / "repo" / "skills"
        claude_skills = tmp_path / "claude" / "skills"
        repo_skills.mkdir(parents=True)
        claude_skills.mkdir(parents=True)

        # Create a skill directory in the repo
        skill_dir = repo_skills / "real-dir-skill"
        skill_dir.mkdir()

        # Create a regular directory (not a symlink) at the claude skills path
        regular_dir = claude_skills / "real-dir-skill"
        regular_dir.mkdir()

        mod.REPO_SKILLS_DIR = repo_skills
        mod.CLAUDE_SKILLS_DIR = claude_skills

        problems = mod.check_symlinks()
        assert problems == []
