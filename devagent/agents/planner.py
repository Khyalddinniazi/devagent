from .base import COMMON_RULES, READ_TOOLS, AgentSpec

SPEC = AgentSpec(
    name="planner",
    system_prompt=f"""You are the Planner agent. You explore a codebase read-only and produce an implementation plan.

Your final message IS the plan, in Markdown, with exactly these sections:
# Plan: <short title>
## Context        - what the request needs and what you learned about the relevant code
## Steps          - numbered, concrete implementation steps
## Files          - files to create/modify (paths), with one-line purpose each
## Test strategy  - which tests to add/update, framework used, how to run them
## Acceptance criteria - checklist a reviewer can verify
## Risks / open questions

Keep it tight and specific to this repository: name real files, functions and commands you found.
Output only the plan as your final message, no preamble.

{COMMON_RULES}""",
    allowed_tools=READ_TOOLS,
    permission_mode="dontAsk",
    disallowed_tools=["Write", "Edit", "MultiEdit", "NotebookEdit", "Bash"],
)


def prompt(task: str, feedback: str | None = None) -> str:
    p = f"Feature request:\n{task}\n\nExplore the repository and write the implementation plan."
    if feedback:
        p += f"\n\nThe reviewer rejected a previous draft with this feedback - address it:\n{feedback}"
    return p
