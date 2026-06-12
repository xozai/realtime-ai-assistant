from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel
from rich import box
from rich.panel import Panel
from rich.table import Table

from realtime_assistant import export as story_export
from realtime_assistant import llm
from realtime_assistant.config import get_settings
from realtime_assistant.confluence_client import ConfluenceClient
from realtime_assistant.coverage import analyze_coverage
from realtime_assistant.events import event_bus
from realtime_assistant.jira_client import JiraClient
from realtime_assistant.logging import (
    console,
    log_clarifying_question,
    log_requirement,
    log_stories,
    logger,
)
from realtime_assistant.memory import DEDUP_SIMILARITY_THRESHOLD, cosine_similarity, memory
from realtime_assistant.models import (
    ConfluenceConfig,
    JiraConfig,
    Requirement,
    RequirementCategory,
    SessionSummary,
    UserStory,
)
from realtime_assistant.notifications import NotificationResult, notify_story_ready
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
        "name": "refine_user_story",
        "description": (
            "Refine or regenerate one existing user story using optional reviewer feedback "
            "and optional selected source requirement IDs. Does not replace unrelated stories."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "story_id": {
                    "type": "string",
                    "description": "The existing user story ID to refine, e.g. US-001.",
                },
                "feedback": {
                    "type": "string",
                    "description": "Reviewer feedback such as split this story or make criteria testable.",
                },
                "requirement_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional exact requirement IDs to use as source context. "
                        "When omitted, the story's current source_requirement_ids are used."
                    ),
                },
            },
            "required": ["story_id"],
            "additionalProperties": False,
        },
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
                },
                "output_dir": {
                    "type": "string",
                    "description": (
                        "Optional export directory. Defaults to the session export directory."
                    ),
                },
                "export_name": {
                    "type": "string",
                    "description": (
                        "Optional base filename without extension. Defaults to user_stories."
                    ),
                },
            },
            "required": ["format"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "submit_stories_to_jira",
        "description": (
            "Submit all generated user stories to a Jira project as Story issues, or preview "
            "the exact Jira payloads with dry_run. Call this after generate_user_stories."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "project_key": {
                    "type": "string",
                    "description": "The Jira project key, e.g. PROJ or MYAPP",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "When true, render Jira payloads without creating issues.",
                },
            },
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "generate_session_summary",
        "description": (
            "Generate a structured executive summary of the discovery call: "
            "overview, key requirements grouped by category, open questions, and risks/assumptions. "
            "Call this near the end of a session after requirements are captured."
        ),
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "analyze_story_coverage",
        "description": (
            "Analyze which captured requirements are covered by generated user stories. "
            "Returns a coverage report with covered, uncovered, and no-stories-yet statuses. "
            "Call this after generate_user_stories to check for gaps before Jira submission."
        ),
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "dedupe_requirements",
        "description": "Report semantically similar requirement pairs using stored embeddings.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "export_to_confluence",
        "description": (
            "Publish a discovery summary page to Confluence containing requirements, "
            "user stories, acceptance criteria, and links to Jira issues. "
            "Call after generate_user_stories (and optionally submit_stories_to_jira). "
            "Requires CONFLUENCE_SPACE_KEY and JIRA_BASE_URL env vars."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Page title. Defaults to 'Discovery: <session_id>' if omitted.",
                },
                "parent_page_id": {
                    "type": "string",
                    "description": "Optional Confluence page ID to nest the new page under.",
                },
                "jira_issue_keys": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional ordered list of Jira issue keys matching the generated "
                        "stories (as returned by submit_stories_to_jira)."
                    ),
                },
            },
            "required": [],
            "additionalProperties": False,
        },
    },
]


async def capture_requirement(requirement: str, category: RequirementCategory) -> dict[str, Any]:
    captured = Requirement(text=requirement.strip(), category=category)
    embedding = await asyncio.to_thread(llm.get_embedding, captured.text)
    captured = captured.model_copy(update={"embedding": embedding})

    similar = memory.find_similar_requirement(embedding, DEDUP_SIMILARITY_THRESHOLD)
    if similar is not None:
        return {
            "ok": True,
            "merged": True,
            "skipped": True,
            "existing_requirement_id": similar.id,
            "message": (
                f"Skipped duplicate requirement; merged with existing requirement {similar.id}."
            ),
            "requirement_count": len(memory.list_requirements()),
        }

    memory.add_requirement(captured)
    confidence = await asyncio.to_thread(
        llm.score_requirement_confidence,
        captured.text,
        captured.category,
        memory.get_current_session(),
    )
    captured.confidence = confidence
    log_requirement(captured)
    await event_bus.publish(
        "requirement_captured",
        requirement_id=captured.id,
        requirement=captured.model_dump(mode="json"),
    )
    return {
        "ok": True,
        "merged": False,
        "skipped": False,
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
    for confidence in ("high", "medium", "low"):
        grouped = [req for req in requirements if req.confidence == confidence]
        if not grouped:
            continue
        table = Table(
            title=f"{confidence.title()} Confidence Requirements",
            header_style="bold cyan",
            box=box.SIMPLE_HEAVY,
        )
        table.add_column("ID")
        table.add_column("Category")
        table.add_column("Requirement")
        for req in grouped:
            table.add_row(req.id, req.category, req.text)
        console.print(table)

    low_confidence = [req for req in requirements if req.confidence == "low"]
    if low_confidence:
        console.print(
            Panel(
                "\n".join(f"{req.id}: {req.text}" for req in low_confidence),
                title="Low-confidence requirements need clarification",
                border_style="yellow",
            )
        )
    return {
        "ok": True,
        "requirements": [req.model_dump(mode="json") for req in requirements],
        "requirement_count": len(requirements),
    }


async def generate_user_stories() -> list[UserStory]:
    requirements = memory.list_requirements()
    settings = get_settings()
    stories = await asyncio.to_thread(
        llm.generate_user_stories,
        requirements,
        model=settings.story_model,
    )
    memory.set_user_stories(stories)
    log_stories(stories)
    await event_bus.publish(
        "stories_generated",
        story_count=len(stories),
        story_ids=[story.id for story in stories],
    )
    return stories


async def refine_user_story(
    story_id: str,
    feedback: str | None = None,
    requirement_ids: list[str] | None = None,
) -> dict[str, Any]:
    story = memory.get_user_story(story_id)
    if story is None:
        return {"ok": False, "error": f"User story {story_id} not found."}

    requirement_context, invalid_requirement_ids = _requirements_for_story_refinement(
        story,
        requirement_ids,
    )
    if invalid_requirement_ids:
        return {
            "ok": False,
            "error": "Unknown requirement IDs: " + ", ".join(invalid_requirement_ids),
            "invalid_requirement_ids": invalid_requirement_ids,
        }

    settings = get_settings()
    refined = await asyncio.to_thread(
        llm.refine_user_story,
        story,
        requirement_context,
        feedback=feedback,
        model=settings.story_model,
    )
    updated = memory.replace_user_story(
        story_id,
        refined,
        feedback=feedback,
        requirement_ids=[requirement.id for requirement in requirement_context],
    )
    if updated is None:
        return {"ok": False, "error": f"User story {story_id} not found."}
    log_stories([updated])
    await event_bus.publish(
        "story_refined",
        story_id=updated.id,
        story=updated.model_dump(mode="json"),
        history_count=len(memory.get_current_session().story_refinement_history),
    )
    return {
        "ok": True,
        "story": updated.model_dump(mode="json"),
        "stories": [item.model_dump(mode="json") for item in memory.list_user_stories()],
        "history_count": len(memory.get_current_session().story_refinement_history),
    }


def _requirements_for_story_refinement(
    story: UserStory,
    requirement_ids: list[str] | None,
) -> tuple[list[Requirement], list[str]]:
    all_requirements = {requirement.id: requirement for requirement in memory.list_requirements()}
    selected_ids = requirement_ids if requirement_ids is not None else story.source_requirement_ids
    deduped_ids: list[str] = []
    invalid_ids: list[str] = []
    for requirement_id in selected_ids:
        normalized = requirement_id.strip()
        if not normalized or normalized in deduped_ids:
            continue
        if normalized not in all_requirements:
            if requirement_ids is not None:
                invalid_ids.append(normalized)
            continue
        deduped_ids.append(normalized)
    return [all_requirements[requirement_id] for requirement_id in deduped_ids], invalid_ids


async def export_user_stories(
    format: str = "all",
    output_dir: str | None = None,
    export_name: str | None = None,
) -> dict[str, Any]:
    stories = memory.list_user_stories()
    session = memory.get_current_session()
    paths = story_export.export_user_stories(
        stories,
        format,
        output_dir=output_dir or memory.export_output_dir or story_export.EXPORTS_DIR,
        export_name=export_name or memory.export_name,
        session_id=session.session_id,
        summary=session.summary,
        requirements=session.requirements,
    )
    absolute_paths = [path.resolve() for path in paths]
    logger.info("Exported user stories: %s", ", ".join(str(path) for path in absolute_paths))
    result = {
        "ok": True,
        "paths": [str(path) for path in absolute_paths],
        "story_count": len(stories),
    }
    notifications = await asyncio.to_thread(
        notify_story_ready,
        story_count=len(stories),
        requirement_count=len(session.requirements),
        export_paths=result["paths"],
    )
    result["notifications"] = _notification_metadata(notifications)
    await event_bus.publish(
        "export_completed",
        ok=result["ok"],
        paths=result["paths"],
        story_count=result["story_count"],
    )
    return result


async def submit_stories_to_jira(
    project_key: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    if not project_key:
        return {
            "ok": False,
            "error": "Jira project_key is required.",
            "warning": (
                "The Jira project key is separate from the discovery project key; "
                "pass the Jira project key explicitly."
            ),
            "discovery_project_key": memory.get_current_session().project_key,
        }

    stories = memory.list_user_stories()
    if dry_run:
        if not stories:
            return {
                "ok": False,
                "error": "No user stories in memory. Run generate_user_stories first.",
            }
        config = JiraConfig(
            base_url=os.environ.get("JIRA_BASE_URL", ""),
            user_email=os.environ.get("JIRA_USER_EMAIL", ""),
            api_token=os.environ.get("JIRA_API_TOKEN", ""),
            story_points_field=os.environ.get("JIRA_STORY_POINTS_FIELD", "story_points"),
        )
    else:
        try:
            config = JiraConfig.from_env()
        except KeyError as exc:
            return {
                "ok": False,
                "error": f"Missing Jira configuration environment variable: {exc.args[0]}",
            }

    try:
        client = JiraClient(config)
        if not dry_run and not client.validate_project(project_key):
            return {
                "ok": False,
                "error": f"Jira project '{project_key}' was not found or is not accessible.",
            }

        if not dry_run:
            stories = memory.list_user_stories()
            if not stories:
                return {
                    "ok": False,
                    "error": "No user stories in memory. Run generate_user_stories first.",
                }

        # Warn if uncovered must-have requirements exist
        session = memory.get_current_session()
        if session.coverage_report is not None:
            uncovered_must_haves = [
                item.requirement_id
                for item in session.coverage_report.items
                if item.status == "uncovered"
                and any(
                    req.id == item.requirement_id and req.category == "functional"
                    for req in session.requirements
                )
            ]
            if uncovered_must_haves:
                console.print(
                    "[yellow]⚠ Warning: submitting to Jira with uncovered requirements: "
                    + ", ".join(uncovered_must_haves)
                    + ". Consider running analyze_story_coverage first.[/yellow]"
                )

        if dry_run:
            results = [
                {
                    **client.preview_issue(project_key, story),
                    "status": "skipped",
                    "skipped_reason": "dry_run",
                }
                for story in stories
            ]
            response = {
                "ok": True,
                "dry_run": True,
                "project_key": project_key,
                "results": results,
                "created_issues": [],
                "count": 0,
                "total_count": len(stories),
                "success_count": 0,
                "failure_count": 0,
                "skipped_count": len(stories),
            }
            notifications = await asyncio.to_thread(
                notify_story_ready,
                story_count=len(stories),
                requirement_count=len(memory.list_requirements()),
            )
            response["notifications"] = _notification_metadata(notifications)
            await event_bus.publish(
                "jira_submission_completed",
                ok=response["ok"],
                dry_run=response["dry_run"],
                project_key=response["project_key"],
                total_count=response["total_count"],
                success_count=response["success_count"],
                failure_count=response["failure_count"],
                skipped_count=response["skipped_count"],
            )
            return response

        results: list[dict[str, Any]] = []
        created_issues: list[str] = []
        for story in stories:
            try:
                issue_key = client.create_issue(project_key, story)
            except Exception as exc:
                results.append(
                    {
                        "story_id": story.id,
                        "title": story.title,
                        "status": "failure",
                        "error": str(exc),
                    }
                )
                continue

            created_issues.append(issue_key)
            results.append(
                {
                    "story_id": story.id,
                    "title": story.title,
                    "status": "success",
                    "issue_key": issue_key,
                    "issue_url": client.issue_url(issue_key),
                }
            )
    except Exception as exc:
        return {"ok": False, "error": f"Failed to submit stories to Jira: {exc}"}

    failure_count = sum(1 for result in results if result["status"] == "failure")
    response = {
        "ok": failure_count == 0,
        "dry_run": False,
        "project_key": project_key,
        "results": results,
        "created_issues": created_issues,
        "count": len(created_issues),
        "total_count": len(stories),
        "success_count": len(created_issues),
        "failure_count": failure_count,
        "skipped_count": 0,
    }
    if failure_count:
        response["error"] = f"{failure_count} Jira issue submission failed."
    notifications = await asyncio.to_thread(
        notify_story_ready,
        story_count=len(stories),
        requirement_count=len(memory.list_requirements()),
        jira_keys=created_issues,
    )
    response["notifications"] = _notification_metadata(notifications)
    await event_bus.publish(
        "jira_submission_completed",
        ok=response["ok"],
        dry_run=response["dry_run"],
        project_key=response["project_key"],
        total_count=response["total_count"],
        success_count=response["success_count"],
        failure_count=response["failure_count"],
        skipped_count=response["skipped_count"],
    )
    return response


def _notification_metadata(results: list[NotificationResult]) -> list[dict[str, Any]]:
    return [
        {
            "notifier": result.notifier,
            "enabled": result.enabled,
            "sent": result.sent,
            **({"error": result.error} if result.error else {}),
        }
        for result in results
    ]


async def generate_session_summary() -> dict[str, Any]:
    requirements = memory.list_requirements()
    clarified_topics = memory.list_clarified_topics()
    summary: SessionSummary = await asyncio.to_thread(
        llm.generate_session_summary, requirements, clarified_topics
    )
    # Store on the current session
    session = memory.get_current_session()
    memory.session = session.model_copy(update={"summary": summary})
    from rich.panel import Panel  # local import to avoid top-level Rich dependency churn
    console.print(
        Panel(
            f"[bold]Overview:[/bold] {summary.overview}\n\n"
            f"[bold]Open Questions:[/bold] {', '.join(summary.open_questions) or 'None'}\n"
            f"[bold]Risks & Assumptions:[/bold] {', '.join(summary.risks_and_assumptions) or 'None'}",
            title="Executive Summary",
            border_style="cyan",
        )
    )
    return {"ok": True, "summary": summary.model_dump(mode="json")}


async def analyze_story_coverage() -> dict[str, Any]:
    session = memory.get_current_session()
    report = analyze_coverage(session)
    memory.session = session.model_copy(update={"coverage_report": report})

    uncovered = [item for item in report.items if item.status == "uncovered"]
    if uncovered:
        console.print(
            f"[yellow]Coverage: {report.coverage_pct}% "
            f"({report.covered_count}/{len(report.items)} requirements covered). "
            f"{len(uncovered)} uncovered: "
            + ", ".join(item.requirement_id for item in uncovered)
            + "[/yellow]"
        )
    else:
        console.print(
            f"[green]Coverage: {report.coverage_pct}% — all requirements covered.[/green]"
        )

    return {"ok": True, "coverage_report": report.model_dump(mode="json")}


async def dedupe_requirements() -> dict[str, Any]:
    requirements = memory.list_requirements()
    duplicates: list[dict[str, Any]] = []

    for left_index, left in enumerate(requirements):
        if left.embedding is None:
            continue
        for right in requirements[left_index + 1 :]:
            if right.embedding is None:
                continue
            similarity = cosine_similarity(left.embedding, right.embedding)
            if similarity >= DEDUP_SIMILARITY_THRESHOLD:
                duplicates.append(
                    {
                        "requirement_id": left.id,
                        "similar_requirement_id": right.id,
                        "similarity": round(similarity, 6),
                        "requirement": left.text,
                        "similar_requirement": right.text,
                    }
                )

    return {
        "ok": True,
        "threshold": DEDUP_SIMILARITY_THRESHOLD,
        "duplicate_pairs": duplicates,
        "duplicate_pair_count": len(duplicates),
        "requirement_count": len(requirements),
    }


async def export_to_confluence(
    title: str | None = None,
    parent_page_id: str | None = None,
    jira_issue_keys: list[str] | None = None,
) -> dict[str, Any]:
    """Publish a discovery summary page to Confluence."""
    try:
        config = ConfluenceConfig.from_env()
    except KeyError as exc:
        return {"ok": False, "error": f"Missing Confluence configuration: {exc.args[0]}"}

    session = memory.get_current_session()
    page_title = title or f"Discovery: {session.session_id}"
    requirements = memory.list_requirements()
    stories = memory.list_user_stories()

    try:
        client = ConfluenceClient(config)
        if not client.validate_space(config.space_key):
            return {
                "ok": False,
                "error": f"Confluence space '{config.space_key}' was not found or is not accessible.",
            }
        page_url = client.export_discovery_page(
            title=page_title,
            requirements=requirements,
            stories=stories,
            summary=session.summary,
            jira_issue_keys=jira_issue_keys,
            parent_page_id=parent_page_id,
        )
    except Exception as exc:
        return {"ok": False, "error": f"Confluence export failed: {exc}"}

    logger.info("Exported discovery page to Confluence: %s", page_url)
    return {
        "ok": True,
        "page_url": page_url,
        "page_title": page_title,
        "requirement_count": len(requirements),
        "story_count": len(stories),
    }


FUNCTION_MAP: dict[str, ToolHandler] = {
    "capture_requirement": capture_requirement,
    "ask_clarifying_question": ask_clarifying_question,
    "summarize_requirements": summarize_requirements,
    "generate_user_stories": generate_user_stories,
    "refine_user_story": refine_user_story,
    "export_user_stories": export_user_stories,
    "submit_stories_to_jira": submit_stories_to_jira,
    "generate_session_summary": generate_session_summary,
    "analyze_story_coverage": analyze_story_coverage,
    "dedupe_requirements": dedupe_requirements,
    "export_to_confluence": export_to_confluence,
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
