from __future__ import annotations

from textwrap import dedent


def system_prompt(memory: str = "", retrieval: str = "", plan: str = "") -> str:
    sections = []
    if memory.strip():
        sections.append("Persistent memory:\n" + memory.strip())
    if retrieval.strip():
        sections.append("Relevant prior work:\n" + retrieval.strip())
    if plan.strip():
        sections.append("Current plan:\n" + plan.strip())
    return dedent(
        """
        You are a coding agent that works inside a local workspace.
        The work loop is: understand the task, inspect the workspace, plan the next action, use tools, verify the result, and stop only when the task is completed.
        Use tools to inspect files, modify code, and run commands.
        Prefer small, reversible changes.
        If a tool fails, inspect the error and recover.
        When the task is solved, respond with a concise final answer.
        If a tool result is unclear, inspect more before guessing.
        """
    ).strip() + ("\n\n" + "\n\n".join(sections) if sections else "")


def planner_prompt() -> str:
    return dedent(
        """
        You are a planning agent for a local coding workspace.
        Create a short actionable plan before editing code.
        Return only JSON with keys:
        - goal: string
        - steps: array of objects with keys title and detail
        - risks: array of strings
        - success_criteria: array of strings
        Keep the plan concrete and small.
        """
    ).strip()


def reflection_prompt() -> str:
    return dedent(
        """
        You are a review agent for a local coding workspace.
        Summarize the outcome after execution.
        Return only JSON with keys:
        - summary: string
        - lessons: array of strings
        - next_steps: array of strings
        - files: array of strings
        - decisions: array of strings
        - preferences: array of strings
        - status: string
        Keep it short and factual.
        """
    ).strip()
