from __future__ import annotations

import json
from pathlib import Path

from pydantic import TypeAdapter

from realtime_assistant.models import UserStory

PROJECT_ROOT = Path(__file__).resolve().parents[2]
JSON_PATH = PROJECT_ROOT / "user_stories.json"
MARKDOWN_PATH = PROJECT_ROOT / "user_stories.md"


def export_to_json(stories: list[UserStory]) -> Path:
    JSON_PATH.write_text(_to_json(stories), encoding="utf-8")
    return JSON_PATH


def export_to_markdown(stories: list[UserStory]) -> Path:
    MARKDOWN_PATH.write_text(_to_markdown(stories), encoding="utf-8")
    return MARKDOWN_PATH


def export_user_stories(stories: list[UserStory], output_format: str = "all") -> list[Path]:
    normalized = output_format.lower().strip()
    paths: list[Path] = []
    if normalized in {"all", "both", "json"}:
        paths.append(export_to_json(stories))
    if normalized in {"all", "both", "markdown", "md"}:
        paths.append(export_to_markdown(stories))
    if not paths:
        raise ValueError("format must be one of: all, both, json, markdown")
    return paths


def _to_json(stories: list[UserStory]) -> str:
    payload = TypeAdapter(list[UserStory]).dump_python(stories, mode="json")
    return json.dumps({"user_stories": payload}, indent=2)


def _to_markdown(stories: list[UserStory]) -> str:
    lines = ["# User Stories", ""]
    if not stories:
        lines.append("_No user stories generated yet._")
        return "\n".join(lines) + "\n"

    for story in stories:
        lines.extend(
            [
                f"## {story.id}: {story.title}",
                "",
                f"**Priority:** {story.priority}",
                f"**Story Points:** {story.story_points}",
                "",
                f"**As a** {story.as_a},",
                f"**I want** {story.i_want},",
                f"**so that** {story.so_that}.",
                "",
                "### Acceptance Criteria",
                "",
            ]
        )
        lines.extend(f"- {criterion}" for criterion in story.acceptance_criteria)
        lines.append("")

    return "\n".join(lines)
