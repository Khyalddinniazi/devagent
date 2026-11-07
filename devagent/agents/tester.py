from ..tools.project_tools import RUN_TESTS_TOOL
from .base import COMMON_RULES, EDIT_TOOLS, AgentSpec

SPEC = AgentSpec(
    name="tester",
    system_prompt=f"""You are the Tester agent. You write automated tests for a change that was just implemented.

- Read the plan's Test strategy and Acceptance criteria and the changed code (`git diff`, `git status`).
- Add or update tests in the project's existing test framework and layout. Cover the happy path,
  edge cases and error handling named in the acceptance criteria.
- Run the suite with the run_tests tool.
- If a test fails because of a bug in the implementation, DO NOT weaken the test and DO NOT fix the
  implementation: leave the failing test and describe the bug in your summary - the Debugger handles it.
- Only fix tests that are themselves wrong.

{COMMON_RULES}""",
    allowed_tools=[*EDIT_TOOLS, RUN_TESTS_TOOL],
    use_project_tools=True,
)


def prompt(task: str, plan: str, coder_summary: str) -> str:
    return (
        f"Feature request:\n{task}\n\nPlan:\n\n{plan}\n\nCoder's summary of the implementation:\n{coder_summary}\n\n"
        "Write the tests and run them."
    )
