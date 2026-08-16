"""Tests for hooks/_lib/ utilities using subprocess invocation."""

import hashlib
import json
import subprocess
import uuid
from pathlib import Path

import pytest


HOOKS_DIR = Path(__file__).resolve().parent.parent  # tests/ -> hooks/


def run_python(code: str, stdin_data: str = "") -> subprocess.CompletedProcess:
    """Run a Python snippet with the hooks dir on sys.path."""
    full_code = f"import sys; sys.path.insert(0, {str(HOOKS_DIR)!r})\n{code}"
    return subprocess.run(
        ["python3", "-c", full_code],
        input=stdin_data,
        capture_output=True,
        text=True,
        timeout=10,
    )


# ---------------------------------------------------------------------------
# parse_event
# ---------------------------------------------------------------------------

class TestParseEvent:
    def test_valid_json(self):
        event = {"tool_name": "Bash", "tool_input": {"command": "ls"}}
        result = run_python(
            "from _lib.event import parse_event; import json; print(json.dumps(parse_event()))",
            stdin_data=json.dumps(event),
        )
        assert result.returncode == 0
        parsed = json.loads(result.stdout)
        assert parsed["tool_name"] == "Bash"

    def test_invalid_json(self):
        result = run_python(
            "from _lib.event import parse_event; import json; print(json.dumps(parse_event()))",
            stdin_data="not json at all",
        )
        assert result.returncode == 0
        parsed = json.loads(result.stdout)
        assert parsed == {}

    def test_empty_string(self):
        result = run_python(
            "from _lib.event import parse_event; import json; print(json.dumps(parse_event()))",
            stdin_data="",
        )
        assert result.returncode == 0
        parsed = json.loads(result.stdout)
        assert parsed == {}


# ---------------------------------------------------------------------------
# get_state_file
# ---------------------------------------------------------------------------

class TestGetStateFile:
    def test_returns_session_specific_path(self):
        session_id = f"test-{uuid.uuid4().hex[:8]}"
        result = run_python(
            "import os\n"
            # Clear higher-priority vars so CLAUDE_SESSION_ID is the winner
            "os.environ.pop('CLAUDE_CODE_SESSION_ID', None)\n"
            f"os.environ['CLAUDE_SESSION_ID'] = {session_id!r}\n"
            "from _lib.state import get_state_file; print(get_state_file('prefix'))",
        )
        assert result.returncode == 0
        path = result.stdout.strip()
        session_hash = hashlib.sha256(session_id.encode()).hexdigest()[:12]
        assert f"prefix-{session_hash}" in path
        assert path.startswith("/tmp/")


# ---------------------------------------------------------------------------
# load_state / save_state
# ---------------------------------------------------------------------------

class TestLoadSaveState:
    def test_missing_file(self, tmp_path):
        missing = tmp_path / "nonexistent.json"
        result = run_python(
            f"from _lib.state import load_state; from pathlib import Path; "
            f"print(load_state(Path({str(missing)!r})))",
        )
        assert result.returncode == 0
        assert "{}" in result.stdout

    def test_valid_file(self, tmp_path):
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps({"key": "value"}))
        result = run_python(
            f"from _lib.state import load_state; from pathlib import Path; import json; "
            f"print(json.dumps(load_state(Path({str(state_file)!r}))))",
        )
        assert result.returncode == 0
        parsed = json.loads(result.stdout)
        assert parsed["key"] == "value"

    def test_corrupt_file(self, tmp_path):
        state_file = tmp_path / "corrupt.json"
        state_file.write_text("not valid json {{{")
        result = run_python(
            f"from _lib.state import load_state; from pathlib import Path; "
            f"print(load_state(Path({str(state_file)!r})))",
        )
        assert result.returncode == 0
        assert "{}" in result.stdout

    def test_save_then_load(self, tmp_path):
        state_file = tmp_path / "roundtrip.json"
        data = {"counter": 42, "items": ["a", "b"]}
        result = run_python(
            f"from _lib.state import save_state, load_state; from pathlib import Path; import json; "
            f"p = Path({str(state_file)!r}); "
            f"save_state(p, {json.dumps(data)}); "
            f"print(json.dumps(load_state(p)))",
        )
        assert result.returncode == 0
        parsed = json.loads(result.stdout)
        assert parsed["counter"] == 42
        assert parsed["items"] == ["a", "b"]


# ---------------------------------------------------------------------------
# extract_git_command
# ---------------------------------------------------------------------------

class TestExtractGitCommand:
    def test_git_commit(self):
        result = run_python(
            'from _lib.git import extract_git_command; '
            'print(extract_git_command("git commit -m \\"foo\\""))',
        )
        assert result.stdout.strip() == "commit"

    def test_not_git_command(self):
        result = run_python(
            'from _lib.git import extract_git_command; '
            'print(extract_git_command("ls -la"))',
        )
        assert result.stdout.strip() == "None"

    def test_git_push(self):
        result = run_python(
            'from _lib.git import extract_git_command; '
            'print(extract_git_command("git push origin main"))',
        )
        assert result.stdout.strip() == "push"

    @pytest.mark.parametrize("command,expected", [
        ("git -C /abs/repo commit -m x", "commit"),
        ("git -c user.name=agent commit -m x", "commit"),
        ("git --work-tree /abs/repo status", "status"),
        ("git --git-dir=/abs/repo/.git push origin main", "push"),
        ("git --no-pager log --oneline", "log"),
    ])
    def test_global_option_does_not_shadow_subcommand(self, command, expected):
        """A git global option between `git` and the subcommand is not the subcommand.

        The old "first non-dash token" rule returned the option's VALUE
        (`/abs/repo`, `user.name=agent`) instead of the subcommand.
        """
        result = run_python(
            'from _lib.git import extract_git_command; '
            f'print(extract_git_command({command!r}))',
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == expected

    def test_bare_git_has_no_subcommand(self):
        result = run_python(
            'from _lib.git import extract_git_command; '
            'print(extract_git_command("git"))',
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "None"


# ---------------------------------------------------------------------------
# is_broad_add
# ---------------------------------------------------------------------------

class TestIsBroadAdd:
    @pytest.mark.parametrize("cmd", [
        "git add -A",
        "git add --all",
        "git add .",
    ])
    def test_broad_add_detected(self, cmd):
        result = run_python(
            f'from _lib.git import is_broad_add; print(is_broad_add({cmd!r}))',
        )
        assert result.stdout.strip() == "True"

    def test_specific_file_not_broad(self):
        result = run_python(
            'from _lib.git import is_broad_add; '
            'print(is_broad_add("git add src/main.py"))',
        )
        assert result.stdout.strip() == "False"


# ---------------------------------------------------------------------------
# block / allow / allow_with_reason
# ---------------------------------------------------------------------------

class TestOutputFunctions:
    def test_block_structure(self):
        result = run_python(
            'from _lib.output import block; block("test reason")',
        )
        parsed = json.loads(result.stdout)
        assert parsed["decision"] == "block"
        assert parsed["reason"] == "test reason"

    def test_allow_structure(self):
        result = run_python(
            'from _lib.output import allow; allow()',
        )
        parsed = json.loads(result.stdout)
        assert parsed["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
        assert parsed["hookSpecificOutput"]["permissionDecision"] == "allow"
        assert "decision" not in parsed

    def test_allow_with_reason_structure(self):
        result = run_python(
            'from _lib.output import allow_with_reason; '
            'allow_with_reason("advisory msg")',
        )
        parsed = json.loads(result.stdout)
        assert parsed["decision"] == "allow"
        assert parsed["reason"] == "advisory msg"


# ---------------------------------------------------------------------------
# update_input (merge semantics)
# ---------------------------------------------------------------------------

class TestUpdateInput:
    """update_input must MERGE `partial` over the event's original tool input.

    CC's updatedInput replaces the tool input wholesale, so the helper merges
    internally. This test fails on the old replace-only implementation, which
    emitted only `partial` and dropped the sibling original fields.
    """

    def test_merges_partial_over_original(self):
        event = {"tool_input": {"prompt": "ORIGINAL", "description": "D", "keep": "K"}}
        code = (
            "from _lib.event import parse_event\n"
            "from _lib import output\n"
            "ev = parse_event()\n"
            "output.update_input(ev, {'prompt': 'WINS'})\n"
        )
        result = run_python(code, stdin_data=json.dumps(event))
        assert result.returncode == 0, result.stderr
        merged = json.loads(result.stdout)["hookSpecificOutput"]["updatedInput"]
        assert merged["prompt"] == "WINS"      # partial wins on key collision
        assert merged["description"] == "D"    # sibling original field preserved
        assert merged["keep"] == "K"           # sibling original field preserved

    def test_non_dict_partial_is_noop(self):
        event = {"tool_input": {"prompt": "P", "description": "D"}}
        code = (
            "import json, sys\n"
            f"sys.path.insert(0, {str(HOOKS_DIR)!r})\n"
            "from _lib.event import parse_event\n"
            "from _lib import output\n"
            "ev = parse_event()\n"
            "output.update_input(ev, ['bad'])\n"
        )
        result = run_python(code, stdin_data=json.dumps(event))
        assert result.returncode == 0, result.stderr
        parsed = json.loads(result.stdout)
        updated = parsed["hookSpecificOutput"]["updatedInput"]
        assert updated["prompt"] == "P"
        assert updated["description"] == "D"

    def test_non_serializable_value_fails_open(self):
        event = {"tool_input": {"prompt": "P"}}
        code = (
            "import sys\n"
            f"sys.path.insert(0, {str(HOOKS_DIR)!r})\n"
            "from _lib.event import parse_event\n"
            "from _lib import output\n"
            "ev = parse_event()\n"
            # Pass a dict with an object() value which is not JSON-serializable
            "output.update_input(ev, {'x': object()})\n"
        )
        result = run_python(code, stdin_data=json.dumps(event))
        assert result.returncode == 0, result.stderr
        parsed = json.loads(result.stdout)
        # Fail-open: emits plain allow (modern shape), NOT updatedInput
        assert parsed["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
        assert parsed["hookSpecificOutput"]["permissionDecision"] == "allow"
        assert "updatedInput" not in parsed["hookSpecificOutput"]
        assert "decision" not in parsed


# ---------------------------------------------------------------------------
# get_session_id env-var precedence
# ---------------------------------------------------------------------------

class TestGetSessionIdPrecedence:
    def test_prefers_claude_code_session_id(self):
        """CLAUDE_CODE_SESSION_ID wins over CLAUDE_SESSION_ID."""
        result = run_python(
            "import os\n"
            "os.environ['CLAUDE_CODE_SESSION_ID'] = 'real-session'\n"
            "os.environ['CLAUDE_SESSION_ID'] = 'legacy'\n"
            "from _lib.state import get_session_id\n"
            "print(get_session_id())\n"
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "real-session"

    def test_falls_back_to_claude_session_id(self):
        """Falls back to CLAUDE_SESSION_ID when CLAUDE_CODE_SESSION_ID is absent."""
        result = run_python(
            "import os\n"
            "os.environ.pop('CLAUDE_CODE_SESSION_ID', None)\n"
            "os.environ['CLAUDE_SESSION_ID'] = 'legacy'\n"
            "os.environ.pop('SESSION_ID', None)\n"
            "from _lib.state import get_session_id\n"
            "print(get_session_id())\n"
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "legacy"

    def test_falls_back_to_session_id(self):
        """Falls back to SESSION_ID when neither CLAUDE_CODE_SESSION_ID nor CLAUDE_SESSION_ID is set."""
        result = run_python(
            "import os\n"
            "os.environ.pop('CLAUDE_CODE_SESSION_ID', None)\n"
            "os.environ.pop('CLAUDE_SESSION_ID', None)\n"
            "os.environ['SESSION_ID'] = 'session-var'\n"
            "from _lib.state import get_session_id\n"
            "print(get_session_id())\n"
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "session-var"

    def test_falls_back_to_pid(self):
        """Falls back to pid-<ppid> when no session env vars are set."""
        result = run_python(
            "import os\n"
            "os.environ.pop('CLAUDE_CODE_SESSION_ID', None)\n"
            "os.environ.pop('CLAUDE_SESSION_ID', None)\n"
            "os.environ.pop('SESSION_ID', None)\n"
            "from _lib.state import get_session_id\n"
            "print(get_session_id())\n"
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip().startswith("pid-")


# ---------------------------------------------------------------------------
# git_invocations / git_subcommands / has_git_subcommand
# ---------------------------------------------------------------------------

# Every spelling of "run this subcommand" that a git global option can wrap.
# `git -C /abs <sub>` is the HOUSE STYLE (~/.claude/command-hygiene.md tells
# agents to prefer `-C` over `cd`), so these are the default path for agent
# commands, not exotic edge cases.
GLOBAL_OPTION_FORMS = [
    "git {sub} target.txt",
    "git -C /abs/repo {sub} target.txt",
    "git -c user.name=agent {sub} target.txt",
    "git --no-pager {sub} target.txt",
    "git --git-dir=/abs/repo/.git {sub} target.txt",
    "git --work-tree /abs/repo {sub} target.txt",
    "git -C /abs/repo -c user.name=agent --no-pager {sub} target.txt",
]


class TestGitSubcommandDetection:
    """Global options between `git` and the subcommand must never hide it.

    git-safety-guard gates on the detected subcommand, so a missed `commit`
    is a silently ungated commit.
    """

    @pytest.mark.parametrize("sub", ["commit", "push", "merge", "add"])
    @pytest.mark.parametrize("form", GLOBAL_OPTION_FORMS)
    def test_subcommand_detected_through_global_options(self, sub, form):
        command = form.format(sub=sub)
        result = run_python(
            'from _lib.git import has_git_subcommand; '
            f'print(has_git_subcommand({command!r}, {sub!r}))',
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "True", f"subcommand missed in: {command}"

    def test_compound_yields_every_invocation(self):
        """`git add f && git -C /a commit` must surface BOTH subcommands."""
        command = "git add file.py && git -C /abs/repo commit -m x"
        result = run_python(
            'from _lib.git import git_subcommands; '
            f'print(sorted(git_subcommands({command!r})))',
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "['add', 'commit']"

    def test_invocations_carry_remaining_args(self):
        command = "git -C /abs/repo commit -m msg && git push origin main"
        result = run_python(
            'from _lib.git import git_invocations; '
            f'print(git_invocations({command!r}))',
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == (
            "[('commit', ['-m', 'msg']), ('push', ['origin', 'main'])]"
        )

    def test_unknown_option_is_skipped_as_a_flag_not_a_value_taker(self):
        """An unrecognised `-x` must NOT consume the next token.

        Treating an unknown option as value-consuming would skip past the real
        subcommand and reopen the detection hole this parser exists to close.
        """
        command = "git --bogus-option commit -m x"
        result = run_python(
            'from _lib.git import has_git_subcommand; '
            f'print(has_git_subcommand({command!r}, "commit"))',
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "True"

    def test_subcommand_argument_is_not_a_subcommand(self):
        """`git log --grep commit` is a log, not a commit."""
        command = "git log --grep commit"
        result = run_python(
            'from _lib.git import git_subcommands, has_git_subcommand; '
            f'print(sorted(git_subcommands({command!r})), '
            f'has_git_subcommand({command!r}, "commit"))',
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "['log'] False"

    @pytest.mark.parametrize("command", [
        "gitk --all",
        "legit commit -m x",
        "git-foo commit",
    ])
    def test_non_git_binaries_do_not_match(self, command):
        result = run_python(
            'from _lib.git import git_subcommands; '
            f'print(sorted(git_subcommands({command!r})))',
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "[]"

    def test_bare_git_yields_no_invocation(self):
        result = run_python(
            'from _lib.git import git_invocations; '
            'print(git_invocations("git"))',
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "[]"

    def test_malformed_quoting_does_not_raise(self):
        """Unbalanced quotes break shlex; the parser must degrade, not explode.

        git-safety-guard blocks CLOSED on an uncaught exception, so a raise here
        would kill every Bash call in the session.
        """
        command = 'git -C "/a commit -m x'
        result = run_python(
            'from _lib.git import has_git_subcommand; '
            f'print(has_git_subcommand({command!r}, "commit"))',
        )
        assert result.returncode == 0, result.stderr
        assert "Traceback" not in result.stderr
        # Fail-safe direction: the commit is still detected, so it stays gated.
        assert result.stdout.strip() == "True"

    @pytest.mark.parametrize("option", [
        "--git-dir=/abs/repo/.git",
        "--git-dir /abs/repo/.git",
    ])
    @pytest.mark.parametrize("sub,other", [("commit", "status"), ("status", "commit")])
    def test_git_dir_pair_proves_real_option_parsing(self, option, sub, other):
        """Same `--git-dir`, two subcommands: each is found, the other is not.

        Pinning `--git-dir=/abs/repo/.git commit` alone would also pass if the
        parser merely noticed the `.git commit` substring. Asserting that the
        SAME option with `status` reports status and NOT commit is what proves
        the option is genuinely consumed.
        """
        command = f"git {option} {sub}"
        result = run_python(
            'from _lib.git import git_subcommands, has_git_subcommand; '
            f'print(sorted(git_subcommands({command!r})), '
            f'has_git_subcommand({command!r}, {other!r}))',
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == f"['{sub}'] False"

    @pytest.mark.parametrize("command", [
        "git --git-dir=/abs/repo/git commit -m x",
        "git --work-tree=/abs/repo/git commit -m x",
    ])
    def test_option_value_ending_in_git_is_not_a_new_invocation(self, command):
        """An option VALUE ending in `/git` must not read as the git binary.

        `_is_git_token` matches any token ending in `/git`; without the
        leading-dash rejection, `--work-tree=/abs/repo/git` starts a phantom
        second invocation and the option is silently dropped.

        The target dir — not the subcommand — is what this pins. The
        subcommand survives the bug by accident (the phantom invocation simply
        consumes the option token and `commit` becomes the next invocation's
        subcommand), so asserting on it alone would pin nothing. The dropped
        option is what points the safety guard at the wrong repository.
        """
        result = run_python(
            'from _lib.git import git_subcommands, git_global_target_dir; '
            f'print(sorted(git_subcommands({command!r})), '
            f'git_global_target_dir({command!r}))',
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "['commit'] /abs/repo/git"

    def test_chain_with_glued_separator_still_finds_the_commit(self):
        """`git add f; git commit -m x` — the `;` does not survive tokenising.

        shlex yields [..., 'f;', 'git', 'commit', ...]. If the arg scan did not
        also stop at a git token, the trailing commit would be absorbed as an
        argument to `add` and escape the gate — a false negative.
        """
        command = "git add f; git commit -m x"
        result = run_python(
            'from _lib.git import git_subcommands; '
            f'print(sorted(git_subcommands({command!r})))',
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "['add', 'commit']"

    def test_has_git_subcommand_accepts_multiple_names(self):
        result = run_python(
            'from _lib.git import has_git_subcommand; '
            'print(has_git_subcommand("git -C /a push origin main", '
            '"commit", "push", "merge"), '
            'has_git_subcommand("git -C /a status", "commit", "push", "merge"))',
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "True False"


# ---------------------------------------------------------------------------
# git_global_target_dir
# ---------------------------------------------------------------------------

class TestGitGlobalTargetDir:
    @pytest.mark.parametrize("command,expected", [
        ("git -C /abs/repo commit -m x", "/abs/repo"),
        ("git --git-dir=/abs/repo/.git commit -m x", "/abs/repo"),
        ("git --git-dir /abs/repo/.git commit -m x", "/abs/repo"),
        ("git --work-tree /abs/repo status", "/abs/repo"),
        # -C outranks --work-tree, which outranks --git-dir.
        ("git --work-tree /via-work-tree -C /via-c status", "/via-c"),
        ("git --git-dir=/via-git-dir/.git --work-tree /via-work-tree status",
         "/via-work-tree"),
        # First -C wins; reconciling divergent targets is TRK-137 territory.
        ("git -C /first status && git -C /second status", "/first"),
        # Regression: an option value whose last segment is literally "git"
        # must survive. This answered None before _is_git_token learned to
        # reject leading-dash tokens, sending the guard at the wrong repo.
        ("git --git-dir=/abs/repo/git status", "/abs/repo/git"),
        ("git -C /abs/repo/git status", "/abs/repo/git"),
        ("git commit -m x", "None"),
        ("ls -la", "None"),
    ])
    def test_target_dir(self, command, expected):
        result = run_python(
            'from _lib.git import git_global_target_dir; '
            f'print(git_global_target_dir({command!r}))',
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == expected


# ---------------------------------------------------------------------------
# resolve_command_target_dir — `git -C` awareness
# ---------------------------------------------------------------------------

class TestResolveCommandTargetDirGitOptions:
    """`cd` sets the base directory; `git -C` then applies relative to it."""

    @staticmethod
    def _resolve(command: str, cwd) -> subprocess.CompletedProcess:
        return run_python(
            f"import os; os.chdir({str(cwd)!r})\n"
            "from _lib.git import resolve_command_target_dir\n"
            f"print(resolve_command_target_dir({command!r}))\n"
        )

    @pytest.fixture
    def dirs(self, tmp_path):
        base = tmp_path / "base"
        other = tmp_path / "other"
        base.mkdir()
        other.mkdir()
        (base / "sub").mkdir()
        return base, other

    def test_c_option_without_cd_wins_over_cwd(self, dirs):
        base, other = dirs
        result = self._resolve(f"git -C {other} commit -m x", base)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == str(other)

    def test_c_option_wins_over_cd(self, dirs):
        base, other = dirs
        result = self._resolve(f"cd {base} && git -C {other} commit -m x", base)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == str(other)

    def test_relative_c_resolves_against_the_cd_base(self, dirs):
        base, other = dirs
        result = self._resolve(f"cd {base} && git -C sub commit -m x", other)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == str(base / "sub")

    def test_git_dir_option_resolves_to_worktree_root(self, dirs):
        base, other = dirs
        result = self._resolve(f"git --git-dir={other}/.git commit -m x", base)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == str(other)

    def test_work_tree_option(self, dirs):
        base, other = dirs
        result = self._resolve(f"git --work-tree {other} status", base)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == str(other)

    def test_first_of_two_conflicting_c_targets_wins(self, dirs):
        base, other = dirs
        command = f"git -C {other} add f && git -C {base} commit -m x"
        result = self._resolve(command, base)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == str(other)

    def test_cd_without_c_is_unchanged(self, dirs):
        base, other = dirs
        result = self._resolve(f"cd {base} && git commit -m x", other)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == str(base)

    def test_no_cd_and_no_c_falls_back_to_cwd(self, dirs):
        base, _other = dirs
        result = self._resolve("git commit -m x", base)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == str(Path(base).resolve())
