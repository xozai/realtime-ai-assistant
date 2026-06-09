from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import TypeAdapter

from realtime_assistant.models import SessionSummary, UserStory

__all__ = [
    "EXPORTS_DIR",
    "ExportOptions",
    "JSON_PATH",
    "MARKDOWN_PATH",
    "export_to_json",
    "export_to_markdown",
    "export_user_stories",
    "format_session_summary_markdown",
    "format_user_story_markdown",
    "format_user_stories_markdown",
    "resolve_export_paths",
    "user_stories_to_json",
]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXPORTS_DIR = PROJECT_ROOT / "exports"
JSON_PATH = PROJECT_ROOT / "user_stories.json"
MARKDOWN_PATH = PROJECT_ROOT / "user_stories.md"
DEFAULT_EXPORT_NAME = "user_stories"


@dataclass(frozen=True)
class ExportOptions:
    """Destination settings for user-story exports."""

    session_id: str
    output_dir: Path | str = EXPORTS_DIR
    export_name: str = DEFAULT_EXPORT_NAME

    def resolve_paths(self) -> dict[str, Path]:
        return resolve_export_paths(
            self.session_id,
            output_dir=self.output_dir,
            export_name=self.export_name,
        )


def resolve_export_paths(
    session_id: str,
    output_dir: Path | str = EXPORTS_DIR,
    export_name: str = DEFAULT_EXPORT_NAME,
) -> dict[str, Path]:
    """Resolve absolute JSON and Markdown paths for a session-aware export."""
    normalized_session_id = _filename_safe(session_id, "session_id")
    normalized_export_name = _filename_safe(export_name, "export_name")
    base_dir = Path(output_dir).expanduser().resolve() / normalized_session_id
    return {
        "json": base_dir / f"{normalized_export_name}.json",
        "markdown": base_dir / f"{normalized_export_name}.md",
    }


def export_to_json(stories: list[UserStory], path: Path | str = JSON_PATH) -> Path:
    """Write user stories as JSON and return the output path."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(user_stories_to_json(stories), encoding="utf-8")
    return output_path


def export_to_markdown(
    stories: list[UserStory],
    path: Path | str = MARKDOWN_PATH,
    *,
    summary: SessionSummary | None = None,
) -> Path:
    """Write user stories (and optional executive summary) as Markdown and return the output path."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(format_user_stories_markdown(stories, summary=summary), encoding="utf-8")
    return output_path


def export_user_stories(
    stories: list[UserStory],
    output_format: str = "all",
    *,
    json_path: Path | str | None = None,
    markdown_path: Path | str | None = None,
    output_dir: Path | str = EXPORTS_DIR,
    export_name: str = DEFAULT_EXPORT_NAME,
    session_id: str | None = None,
    summary: SessionSummary | None = None,
) -> list[Path]:
    """Export user stories to JSON, Markdown, or both.

    ``output_format`` accepts ``all``/``both``, ``json``, or
    ``markdown``/``md``. By default, exports are written below
    ``exports/<session_id>/`` so generated output does not overwrite the root
    sample files. Explicit path arguments are still supported for callers that
    need full control.
    """
    normalized = output_format.lower().strip()
    writes_json = normalized in {"all", "both", "json"}
    writes_markdown = normalized in {"all", "both", "markdown", "md"}
    if not writes_json and not writes_markdown:
        raise ValueError("format must be one of: all, both, json, markdown")

    resolved_paths: dict[str, Path] | None = None
    if (writes_json and json_path is None) or (writes_markdown and markdown_path is None):
        if session_id is None:
            raise ValueError("session_id is required unless explicit export paths are provided.")
        resolved_paths = resolve_export_paths(session_id, output_dir, export_name)

    if json_path is None:
        output_json_path = resolved_paths["json"] if resolved_paths is not None else JSON_PATH
    else:
        output_json_path = Path(json_path)
    if markdown_path is None:
        output_markdown_path = (
            resolved_paths["markdown"] if resolved_paths is not None else MARKDOWN_PATH
        )
    else:
        output_markdown_path = Path(markdown_path)

    paths: list[Path] = []
    if writes_json:
        paths.append(export_to_json(stories, output_json_path))
    if writes_markdown:
        paths.append(export_to_markdown(stories, output_markdown_path, summary=summary))
    return paths


def user_stories_to_json(stories: list[UserStory]) -> str:
    """Format user stories as the public JSON export payload."""
    payload = TypeAdapter(list[UserStory]).dump_python(stories, mode="json")
    return json.dumps({"user_stories": payload}, indent=2)


def format_session_summary_markdown(summary: SessionSummary) -> str:
    """Format a SessionSummary as a Markdown section."""
    lines = ["## Executive Summary", "", summary.overview, ""]

    if summary.key_requirements:
        lines.append("### Key Requirements")
        lines.append("")
        for category, reqs in summary.key_requirements.items():
            lines.append(f"**{category.capitalize()}**")
            lines.extend(f"- {req}" for req in reqs)
            lines.append("")

    if summary.open_questions:
        lines.append("### Open Questions")
        lines.append("")
        lines.extend(f"- {q}" for q in summary.open_questions)
        lines.append("")

    if summary.risks_and_assumptions:
        lines.append("### Risks & Assumptions")
        lines.append("")
        lines.extend(f"- {r}" for r in summary.risks_and_assumptions)
        lines.append("")

    return "\n".join(lines)


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


def format_user_stories_markdown(
    stories: list[UserStory],
    *,
    summary: SessionSummary | None = None,
) -> str:
    """Format a collection of user stories as a complete Markdown document."""
    lines = ["# User Stories", ""]

    if summary is not None:
        lines.append(format_session_summary_markdown(summary))
        lines.append("")

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


def _filename_safe(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be blank.")
    if Path(normalized).name != normalized:
        raise ValueError(f"{field_name} must be a filename-safe value, not a path.")
    return normalized
