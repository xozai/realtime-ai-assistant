from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel
from rich.table import Table

from realtime_assistant import export as story_export
from realtime_assistant import llm
from realtime_assistant.jira_client import JiraClient
from realtime_assistant.logging import (
    console,
    log_clarifying_question,
    log_requirement,
    log_stories,
    logger,
)
from realtime_assistant.memory import memory
from realtime_assistant.models import JiraConfig, RequirementCategory, UserStory
from realtime_assistant.transcript import TranscriptWriter

ToolHandler = Callable[..., Awaitable[Any]]


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "capture_requirement",
        "description": "Capture a clear requirement discovered during the conversation.",
        "parameters": {
            "type": "object",
            "properties": {
                "requirement": {
                    "type": "string",
                    "description": "A concise statement of the requirement.",
                },
                "category": {
                    "type": "string",
                    "enum": ["functional", "non-functional", "constraint", "assumption"],
                },
            },
            "required": ["requirement", "category"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "ask_clarifying_question",
        "description": "Track and ask a clarifying question for a vague discovery topic.",
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "question": {"type": "string"},
            },
            "required": ["topic", "question"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "summarize_requirements",
        "description": "Print all requirements captured so far to the terminal.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "generate_user_stories",
        "description": "Generate structured Agile user stories from captured requirements.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "export_user_stories",
        "description": "Export generated user stories to JSON, Markdown, or both.",
        "parameters": {
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "enum": ["all", "both", "json", "markdown", "md"],
                    "description": "Export format. Use all or both to write JSON and Markdown files.",
                }
            },
            "required": ["format"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "submit_stories_to_jira",
        "description": (
            "Submit all generated user stories to a Jira project as Story issues. "
            "Call this after generate_user_stories. Returns the created Jira issue keys."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "project_key": {
                    "type": "string",
                    "description": "The Jira project key, e.g. PROJ or MYAPP",
                }
            },
            "required": ["project_key"],
            "additionalProperties": False,
        },
    },
]


async def capture_requirement(requirement: str, category: RequirementCategory) -> dict[str, Any]:
    captured = memory.create_requirement(requirement, category)
    log_requirement(captured)
    return {
        "ok": True,
        "requirement": captured.model_dump(mode="json"),
        "requirement_count": len(memory.list_requirements()),
    }


async def ask_clarifying_question(topic: str, question: str) -> dict[str, Any]:
    memory.mark_clarified(topic)
    log_clarifying_question(topic, question)
    return {
        "ok": True,
        "topic": topic,
        "question": question,
        "clarified_topics": memory.list_clarified_topics(),
    }


async def summarize_requirements() -> dict[str, Any]:
    requirements = memory.list_requirements()
    table = Table(title="Captured Requirements", header_style="bold cyan")
    table.add_column("ID")
    table.add_column("Category")
    table.add_column("Requirement")
    for req in requirements:
        table.add_row(req.id, req.category, req.text)
    console.print(table)
    return {
        "ok": True,
        "requirements": [req.model_dump(mode="json") for req in requirements],
        "requirement_count": len(requirements),
    }


async def generate_user_stories() -> list[UserStory]:
    requirements = memory.list_requirements()
    stories = await asyncio.to_thread(llm.generate_user_stories, requirements)
    memory.set_user_stories(stories)
    log_stories(stories)
    return stories


async def export_user_stories(format: str = "all") -> dict[str, Any]:
    stories = memory.list_user_stories()
    paths = story_export.export_user_stories(stories, format)
    logger.info("Exported user stories: %s", ", ".join(str(path) for path in paths))
    return {"ok": True, "paths": [str(path) for path in paths], "story_count": len(stories)}


async def submit_stories_to_jira(project_key: str) -> dict[str, Any]:
    try:
        config = JiraConfig.from_env()
    except KeyError as exc:
        return {"ok": False, "error": f"Missing Jira configuration environment variable: {exc.args[0]}"}

    try:
        client = JiraClient(config)
        if not client.validate_project(project_key):
            return {
                "ok": False,
                "error": f"Jira project '{project_key}' was not found or is not accessible.",
            }

        stories = memory.list_user_stories()
        if not stories:
            return {
                "ok": False,
                "error": "No user stories in memory. Run generate_user_stories first.",
            }

        created_issues = [client.create_issue(project_key, story) for story in stories]
    except Exception as exc:
        return {"ok": False, "error": f"Failed to submit stories to Jira: {exc}"}

    return {
        "ok": True,
        "project_key": project_key,
        "created_issues": created_issues,
        "count": len(created_issues),
    }


FUNCTION_MAP: dict[str, ToolHandler] = {
    "capture_requirement": capture_requirement,
    "ask_clarifying_question": ask_clarifying_question,
    "summarize_requirements": summarize_requirements,
    "generate_user_stories": generate_user_stories,
    "export_user_stories": export_user_stories,
    "submit_stories_to_jira": submit_stories_to_jira,
}


def to_json_safe(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [to_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [to_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: to_json_safe(item) for key, item in value.items()}
    return value


async def dispatch_tool(
    name: str,
    arguments_json: str | None,
    transcript: TranscriptWriter | None = None,
) -> Any:
    handler = FUNCTION_MAP.get(name)
    if handler is None:
        result = {"ok": False, "error": f"Unknown tool: {name}"}
        if transcript is not None:
            transcript.record_tool_call(name, {})
            transcript.record_tool_result(name, result)
        return result
    try:
        arguments = json.loads(arguments_json or "{}")
    except json.JSONDecodeError as exc:
        result = {"ok": False, "error": f"Invalid JSON arguments: {exc}"}
        if transcript is not None:
            transcript.record_tool_call(name, arguments_json or "")
            transcript.record_tool_result(name, result)
        return result

    if transcript is not None:
        transcript.record_tool_call(name, arguments)

    try:
        result = to_json_safe(await handler(**arguments))
    except Exception as exc:
        logger.exception("Tool %s failed", name)
        result = {"ok": False, "error": str(exc)}
    if transcript is not None:
        transcript.record_tool_result(name, result)
    return result
