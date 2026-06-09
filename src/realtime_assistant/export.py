from __future__ import annotations

import json
from pathlib import Path

from pydantic import TypeAdapter

from realtime_assistant.models import UserStory

__all__ = [
    "JSON_PATH",
    "MARKDOWN_PATH",
    "export_to_json",
    "export_to_markdown",
    "export_user_stories",
    "format_user_story_markdown",
    "format_user_stories_markdown",
    "user_stories_to_json",
]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
JSON_PATH = PROJECT_ROOT / "user_stories.json"
MARKDOWN_PATH = PROJECT_ROOT / "user_stories.md"


def export_to_json(stories: list[UserStory], path: Path | str = JSON_PATH) -> Path:
    """Write user stories as JSON and return the output path."""
    output_path = Path(path)
    output_path.write_text(user_stories_to_json(stories), encoding="utf-8")
    return output_path


def export_to_markdown(stories: list[UserStory], path: Path | str = MARKDOWN_PATH) -> Path:
    """Write user stories as Markdown and return the output path."""
    output_path = Path(path)
    output_path.write_text(format_user_stories_markdown(stories), encoding="utf-8")
    return output_path


def export_user_stories(
    stories: list[UserStory],
    output_format: str = "all",
    *,
    json_path: Path | str = JSON_PATH,
    markdown_path: Path | str = MARKDOWN_PATH,
) -> list[Path]:
    """Export user stories to JSON, Markdown, or both.

    ``output_format`` accepts ``all``/``both``, ``json``, or
    ``markdown``/``md``. The default paths preserve the original CLI behavior,
    while path arguments make the function testable without touching project
    root files.
    """
    normalized = output_format.lower().strip()
    paths: list[Path] = []
    if normalized in {"all", "both", "json"}:
        paths.append(export_to_json(stories, json_path))
    if normalized in {"all", "both", "markdown", "md"}:
        paths.append(export_to_markdown(stories, markdown_path))
    if not paths:
        raise ValueError("format must be one of: all, both, json, markdown")
    return paths


def user_stories_to_json(stories: list[UserStory]) -> str:
    """Format user stories as the public JSON export payload."""
    payload = TypeAdapter(list[UserStory]).dump_python(stories, mode="json")
    return json.dumps({"user_stories": payload}, indent=2)


def format_user_story_markdown(story: UserStory) -> str:
    """Format a single user story as a Markdown section."""
    lines = [
        f"## {story.id}: {story.title}",
        "",
        f"**Priority:** {story.priority}",
        f"**Story Points:** {story.story_points}",
        f"**Source Requirements:** {', '.join(story.source_requirement_ids) or 'None'}",
        "",
        f"**As a** {story.as_a},",
        f"**I want** {story.i_want},",
        f"**so that** {story.so_that}.",
        "",
        "### Acceptance Criteria",
        "",
    ]
    lines.extend(f"- {criterion}" for criterion in story.acceptance_criteria)
    return "\n".join(lines)


def format_user_stories_markdown(stories: list[UserStory]) -> str:
    """Format a collection of user stories as a complete Markdown document."""
    lines = ["# User Stories", ""]
    if not stories:
        lines.append("_No user stories generated yet._")
        return "\n".join(lines) + "\n"

    for story in stories:
        lines.append(format_user_story_markdown(story))
        lines.append("")

    return "\n".join(lines)


def _to_json(stories: list[UserStory]) -> str:
    """Compatibility wrapper for older internal tests/imports."""
    return user_stories_to_json(stories)


def _to_markdown(stories: list[UserStory]) -> str:
    """Compatibility wrapper for older internal tests/imports."""
    return format_user_stories_markdown(stories)
