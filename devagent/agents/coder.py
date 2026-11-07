from ..tools.project_tools import RUN_TESTS_TOOL
from .base import COMMON_RULES, EDIT_TOOLS, AgentSpec

SPEC = AgentSpec(
    name="coder",
    system_prompt=f"""You are the Coder agent. You implement an approved plan in the repository.

- Implement every step of the plan; keep changes minimal and focused.
- Do not write the new tests yourself unless the plan says the change cannot be verified otherwise -
  a separate Tester agent writes tests next. Do keep existing tests passing.
- You may run the existing test suite with the run_tests tool or Bash to check you broke nothing.

{COMMON_RULES}""",
    allowed_tools=[*EDIT_TOOLS, RUN_TESTS_TOOL],
    use_project_tools=True,
)


def prompt(task: str, plan: str) -> str:
    return f"Feature request:\n{task}\n\nApproved plan:\n\n{plan}\n\nImplement it now."
