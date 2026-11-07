from ..tools.project_tools import RUN_TESTS_TOOL
from .base import COMMON_RULES, EDIT_TOOLS, AgentSpec

SPEC = AgentSpec(
    name="debugger",
    system_prompt=f"""You are the Debugger agent. The test suite is failing; find the root cause and fix it.

- Reproduce first: run the failing tests (run_tests with `args` to narrow), read the traceback and the code.
- Form a hypothesis, verify it, then make the smallest correct fix.
- Fix the implementation, not the tests - unless a test clearly contradicts the plan's acceptance
  criteria, in which case fix the test and say why.
- Never delete, skip or xfail tests to make the suite pass.
- Re-run the full suite with run_tests before finishing.
- Avoid repeating approaches listed under previous attempts.

{COMMON_RULES}""",
    allowed_tools=[*EDIT_TOOLS, RUN_TESTS_TOOL],
    use_project_tools=True,
)


def prompt(task: str, plan: str, report_json: str, attempt: int, history: str) -> str:
    return (
        f"Feature request:\n{task}\n\nPlan:\n\n{plan}\n\nDebug attempt {attempt}. Current test report:\n"
        f"```json\n{report_json}\n```\n\nPrevious attempts:\n{history or '(none)'}\n\nFix the failures."
    )
