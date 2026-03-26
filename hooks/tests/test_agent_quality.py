"""LLM-as-Judge quality tests for agent behavioral contracts.

These tests invoke real claude CLI calls and are EXPENSIVE (~$0.05 per agent test).
They are skipped by default and only run with: pytest --run-llm-judge

Each test:
1. Sends a realistic prompt to an agent via `claude --agent-file`
2. Captures the agent's output
3. Sends the output to a second claude call acting as a judge
4. Asserts the judge returns PASS
"""

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest


AGENTS_DIR = Path("/Users/cevin/.claude/skills/coding-team/agents")

SIMPLE_DIFF = """\
diff --git a/lib.py b/lib.py
index 1234567..abcdefg 100644
--- a/lib.py
+++ b/lib.py
@@ -1,3 +1,5 @@
 def greet(name):
-    return "Hello, " + name
+    greeting = "Hello, "
+    result = greeting + name
+    return result
"""

SIMPLE_SPEC_AND_DIFF = """\
Spec: The greet() function should accept a name parameter and return "Hello, {name}".

Diff:
diff --git a/lib.py b/lib.py
--- a/lib.py
+++ b/lib.py
@@ -1,2 +1,2 @@
 def greet(name):
-    return "Hi, " + name
+    return "Hello, " + name
"""


@dataclass
class AgentContract:
    """Behavioral contract for an agent under test."""

    agent_file: str
    test_prompt: str
    expected_behaviors: list[str]
    forbidden_behaviors: list[str]
    identity_check: str
    description: str


AGENT_CONTRACTS: dict[str, AgentContract] = {
    "ct-implementer": AgentContract(
        agent_file="ct-implementer.md",
        test_prompt=(
            "Implement: add a hello() function to lib.py that returns 'hello'. "
            "Working directory: /tmp/test-agent-quality. "
            "No tests required for this trivial function."
        ),
        expected_behaviors=["DONE", "hello"],
        forbidden_behaviors=[],
        identity_check="implementer",
        description=(
            "The implementer agent should attempt to write code and report "
            "DONE or BLOCKED. It should understand its role as an implementer."
        ),
    ),
    "ct-simplify-auditor": AgentContract(
        agent_file="ct-simplify-auditor.md",
        test_prompt=(
            f"Review this diff for unnecessary complexity:\n\n{SIMPLE_DIFF}\n\n"
            "Report findings or state 'Zero findings' if the code is clean."
        ),
        expected_behaviors=["finding", "complexity"],
        forbidden_behaviors=["Edit", "Write", "I'll fix"],
        identity_check="simplify auditor",
        description=(
            "The simplify auditor should analyze the diff for complexity issues "
            "and report findings. It must NOT attempt to edit or fix code."
        ),
    ),
    "ct-harden-auditor": AgentContract(
        agent_file="ct-harden-auditor.md",
        test_prompt=(
            f"Review this diff for security and robustness issues:\n\n{SIMPLE_DIFF}\n\n"
            "Report findings or state 'Zero findings' if the code is clean."
        ),
        expected_behaviors=["finding"],
        forbidden_behaviors=["Edit", "Write", "I'll fix"],
        identity_check="harden auditor",
        description=(
            "The harden auditor should analyze the diff for security/robustness "
            "issues and report findings. It must NOT attempt to edit or fix code."
        ),
    ),
    "ct-spec-reviewer": AgentContract(
        agent_file="ct-spec-reviewer.md",
        test_prompt=(
            f"Verify this implementation matches the spec:\n\n{SIMPLE_SPEC_AND_DIFF}\n\n"
            "Report PASS if it matches, FAIL if it does not."
        ),
        expected_behaviors=["PASS"],
        forbidden_behaviors=["Edit", "Write"],
        identity_check="spec reviewer",
        description=(
            "The spec reviewer should compare the diff against the spec and "
            "report PASS or FAIL. It must NOT attempt to edit code."
        ),
    ),
    "ct-harness-engineer": AgentContract(
        agent_file="ct-harness-engineer.md",
        test_prompt=(
            "Audit the harness at ~/.claude/. Examine hooks, rules, and settings. "
            "Report findings organized by the four verbs. Include a maturity level assessment."
        ),
        expected_behaviors=["constrain", "inform", "verify", "correct"],
        forbidden_behaviors=["I'll implement", "Edit tool"],
        identity_check="harness engineer",
        description=(
            "The harness engineer should audit the harness infrastructure, mention "
            "the four verbs (constrain, inform, verify, correct), and assess maturity level. "
            "It must NOT attempt to implement changes directly."
        ),
    ),
}


def _claude_cli_available() -> bool:
    """Check if the claude CLI is installed and accessible."""
    return shutil.which("claude") is not None


def _run_agent(agent_name: str, prompt: str, timeout_seconds: int = 60) -> str:
    """Run an agent via claude CLI and return its output."""
    agent_path = str(AGENTS_DIR / AGENT_CONTRACTS[agent_name].agent_file)
    result = subprocess.run(
        [
            "claude",
            "--agent-file", agent_path,
            "-p", prompt,
            "--max-turns", "3",
        ],
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    return result.stdout + result.stderr


def _judge_output(agent_name: str, contract: AgentContract, agent_output: str,
                  timeout_seconds: int = 30) -> dict:
    """Use a second claude call to judge the agent's output against its contract."""
    expected_list = "\n".join(f"  - {behavior}" for behavior in contract.expected_behaviors)
    forbidden_list = "\n".join(f"  - {behavior}" for behavior in contract.forbidden_behaviors)

    judge_prompt = f"""You are evaluating an AI agent's output for compliance with its behavioral contract.

Agent: {agent_name}
Contract: {contract.description}
Identity check: The agent should demonstrate it understands its role as a "{contract.identity_check}"

Expected behaviors (these MUST appear in the output, case-insensitive):
{expected_list}

Forbidden behaviors (these must NOT appear in the output):
{forbidden_list if forbidden_list else "  (none)"}

Agent output:
---
{agent_output[:8000]}
---

Evaluate:
1. Did the agent follow its identity? (yes/no + evidence)
2. Did all expected behaviors appear? (checklist — case-insensitive match counts)
3. Did any forbidden behaviors appear? (checklist)
4. Overall: PASS / FAIL

Respond ONLY with valid JSON, no markdown fences:
{{"identity": true/false, "expected": {{"behavior_text": true/false, ...}}, "forbidden": {{"behavior_text": true/false, ...}}, "overall": "PASS" or "FAIL", "reasoning": "brief explanation"}}"""

    result = subprocess.run(
        [
            "claude",
            "-p", judge_prompt,
            "--max-turns", "1",
            "--output-format", "json",
        ],
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )

    raw = result.stdout.strip()

    # The JSON output format wraps the response — extract the result field
    try:
        wrapper = json.loads(raw)
        if isinstance(wrapper, dict) and "result" in wrapper:
            raw = wrapper["result"]
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    # Try parsing the judge's JSON response
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        # If the judge didn't return valid JSON, construct a failure
        return {
            "identity": False,
            "expected": {},
            "forbidden": {},
            "overall": "FAIL",
            "reasoning": f"Judge did not return valid JSON. Raw output: {raw[:500]}",
        }


SKIP_REASON = "LLM judge tests are expensive (~$0.05 each). Use --run-llm-judge to enable."
SKIP_NO_CLI = "claude CLI not found in PATH. Install it to run LLM judge tests."


@pytest.mark.llm_judge
class TestAgentBehavioralContracts:
    """Parametrized LLM-as-judge tests for agent behavioral contracts."""

    @pytest.fixture(autouse=True)
    def _check_llm_judge_enabled(self, request):
        """Skip unless --run-llm-judge was passed."""
        if not request.config.getoption("--run-llm-judge", default=False):
            pytest.skip(SKIP_REASON)
        if not _claude_cli_available():
            pytest.skip(SKIP_NO_CLI)

    @pytest.mark.parametrize(
        "agent_name",
        list(AGENT_CONTRACTS.keys()),
        ids=list(AGENT_CONTRACTS.keys()),
    )
    def test_agent_contract_compliance(self, agent_name: str):
        """Verify agent output satisfies its behavioral contract via LLM judge.

        Cost estimate: ~$0.05 per agent (agent call + judge call).
        """
        contract = AGENT_CONTRACTS[agent_name]

        # Step 1: Run the agent
        agent_output = _run_agent(agent_name, contract.test_prompt)
        assert agent_output.strip(), (
            f"Agent {agent_name} produced no output. "
            f"Check that the agent file exists: {AGENTS_DIR / contract.agent_file}"
        )

        # Step 2: Judge the output
        verdict = _judge_output(agent_name, contract, agent_output)

        # Step 3: Report and assert
        reasoning = verdict.get("reasoning", "No reasoning provided")
        overall = verdict.get("overall", "FAIL")

        # Build a detailed failure message
        details = [
            f"Agent: {agent_name}",
            f"Overall: {overall}",
            f"Identity OK: {verdict.get('identity', 'unknown')}",
            f"Expected: {json.dumps(verdict.get('expected', {}), indent=2)}",
            f"Forbidden: {json.dumps(verdict.get('forbidden', {}), indent=2)}",
            f"Reasoning: {reasoning}",
            f"--- Agent output (first 2000 chars) ---",
            agent_output[:2000],
        ]

        assert overall == "PASS", "\n".join(details)
