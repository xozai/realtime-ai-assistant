from __future__ import annotations

import json
from pathlib import Path

from realtime_assistant import export
from realtime_assistant.models import UserStory


def test_export_to_json_writes_valid_file(sample_user_story: UserStory) -> None:
    path = export.export_to_json([sample_user_story])
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert path == export.JSON_PATH
    assert payload["user_stories"][0]["title"] == "Email login"
    assert payload["user_stories"][0]["priority"] == "must-have"
    assert "Given a registered user" in payload["user_stories"][0]["acceptance_criteria"][0]


def test_export_to_json_accepts_custom_path(sample_user_story: UserStory, tmp_path: Path) -> None:
    output_path = tmp_path / "stories.json"

    path = export.export_to_json([sample_user_story], output_path)

    assert path == output_path
    assert json.loads(output_path.read_text(encoding="utf-8"))["user_stories"][0]["id"] == "US-001"


def test_export_to_markdown_writes_valid_file(sample_user_story: UserStory) -> None:
    path = export.export_to_markdown([sample_user_story])
    content = path.read_text(encoding="utf-8")
    assert path == export.MARKDOWN_PATH
    assert "Email login" in content
    assert "**Priority:** must-have" in content
    assert "Given a registered user" in content


def test_format_user_story_markdown_is_testable_without_file_io(
    sample_user_story: UserStory,
) -> None:
    content = export.format_user_story_markdown(sample_user_story)

    assert content.startswith("## US-001: Email login")
    assert "**Story Points:** 3" in content
    assert "- Given a registered user" in content


def test_format_user_stories_markdown_includes_document_title(
    sample_user_story: UserStory,
) -> None:
    content = export.format_user_stories_markdown([sample_user_story])

    assert content.startswith("# User Stories\n\n## US-001: Email login")


def test_user_stories_to_json_formats_public_payload(sample_user_story: UserStory) -> None:
    payload = json.loads(export.user_stories_to_json([sample_user_story]))

    assert payload == {
        "user_stories": [sample_user_story.model_dump(mode="json")],
    }


def test_export_user_stories_accepts_custom_paths(
    sample_user_story: UserStory,
    tmp_path: Path,
) -> None:
    json_path = tmp_path / "stories.json"
    markdown_path = tmp_path / "stories.md"

    paths = export.export_user_stories(
        [sample_user_story],
        "both",
        json_path=json_path,
        markdown_path=markdown_path,
    )

    assert paths == [json_path, markdown_path]
    assert json_path.exists()
    assert markdown_path.exists()


def test_empty_exports_are_valid() -> None:
    json_path = export.export_to_json([])
    markdown_path = export.export_to_markdown([])
    assert json.loads(json_path.read_text(encoding="utf-8")) == {"user_stories": []}
    assert "_No user stories generated yet._" in markdown_path.read_text(encoding="utf-8")


def test_repeated_exports_overwrite_cleanly(sample_user_story: UserStory) -> None:
    export.export_to_json([])
    export.export_to_markdown([])
    export.export_to_json([sample_user_story])
    export.export_to_markdown([sample_user_story])
    assert len(json.loads(Path(export.JSON_PATH).read_text(encoding="utf-8"))["user_stories"]) == 1
    assert "_No user stories generated yet._" not in Path(export.MARKDOWN_PATH).read_text(
        encoding="utf-8"
    )
