from .base import AgentSpec

SPEC = AgentSpec(
    name="writer",
    system_prompt="You write concise, accurate GitHub pull request descriptions in Markdown. "
    "Output only the PR body - no title line, no preamble.",
    allowed_tools=[],
    permission_mode="dontAsk",
    disallowed_tools=["Read", "Glob", "Grep", "Write", "Edit", "MultiEdit", "NotebookEdit", "Bash", "WebFetch", "WebSearch"],
)


def prompt(task: str, plan: str, diff_stat: str, test_summary: str) -> str:
    return (
        f"Write the PR body for this change.\n\nRequest: {task}\n\nPlan:\n{plan}\n\nDiff stat:\n{diff_stat}\n\n"
        f"Tests: {test_summary}\n\nSections: ## Summary (2-4 bullets), ## Changes, ## Testing."
    )
