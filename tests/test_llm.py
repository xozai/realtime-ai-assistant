from __future__ import annotations

from realtime_assistant.llm import validate_story_source_requirement_ids
from realtime_assistant.models import Requirement, UserStory


def make_story(source_requirement_ids: list[str]) -> UserStory:
    return UserStory(
        id="US-001",
        title="Email login",
        as_a="registered user",
        i_want="to log in with email",
        so_that="I can access my account",
        source_requirement_ids=source_requirement_ids,
        acceptance_criteria=["Given valid credentials, then access is granted."],
        priority="must-have",
        story_points=3,
    )


def make_requirements() -> list[Requirement]:
    return [
        Requirement(id="REQ-001", text="Users can log in", category="functional"),
        Requirement(id="REQ-002", text="Users can reset passwords", category="functional"),
    ]


def test_validate_story_source_requirement_ids_keeps_valid_current_ids() -> None:
    stories = validate_story_source_requirement_ids(
        [make_story(["REQ-001", "REQ-404", "REQ-001"])],
        make_requirements(),
    )

    assert stories[0].source_requirement_ids == ["REQ-001"]


def test_validate_story_source_requirement_ids_falls_back_when_missing_or_invalid() -> None:
    stories = validate_story_source_requirement_ids(
        [make_story(["REQ-404"])],
        make_requirements(),
    )

    assert stories[0].source_requirement_ids == ["REQ-001", "REQ-002"]


def test_validate_story_source_requirement_ids_clears_ids_without_requirements() -> None:
    stories = validate_story_source_requirement_ids([make_story(["REQ-001"])], [])

    assert stories[0].source_requirement_ids == []
