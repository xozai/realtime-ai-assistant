from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from realtime_assistant.models import DiscoverySession, Requirement, UserStory


def test_requirement_valid_instantiation(sample_requirement: Requirement) -> None:
    assert sample_requirement.id == "REQ-001"
    assert sample_requirement.text == "Users can log in with email"
    assert sample_requirement.category == "functional"
    assert sample_requirement.captured_at.tzinfo is not None


def test_user_story_valid_instantiation(sample_user_story: UserStory) -> None:
    assert sample_user_story.title == "Email login"
    assert sample_user_story.priority == "must-have"
    assert sample_user_story.story_points == 3
    assert sample_user_story.source_requirement_ids == ["REQ-001"]
    assert len(sample_user_story.acceptance_criteria) == 2


def test_user_story_source_requirement_ids_are_required() -> None:
    with pytest.raises(ValidationError):
        UserStory(
            id="US-001",
            title="Missing source IDs",
            as_a="user",
            i_want="a feature",
            so_that="I get value",
            priority="must-have",
            story_points=3,
        )


def test_user_story_schema_requires_source_requirement_ids() -> None:
    schema = UserStory.model_json_schema()

    assert "source_requirement_ids" in schema["required"]


def test_user_story_source_requirement_ids_reject_blank_values() -> None:
    with pytest.raises(ValidationError):
        UserStory(
            id="US-001",
            title="Blank source ID",
            as_a="user",
            i_want="a feature",
            so_that="I get value",
            source_requirement_ids=["REQ-001", " "],
            priority="must-have",
            story_points=3,
        )


def test_invalid_requirement_category_raises() -> None:
    with pytest.raises(ValidationError):
        Requirement(text="Users can log in", category="invalid")


def test_invalid_priority_raises() -> None:
    with pytest.raises(ValidationError):
        UserStory(
            id="US-001",
            title="Bad priority",
            as_a="user",
            i_want="a feature",
            so_that="I get value",
            source_requirement_ids=["REQ-001"],
            priority="urgent",
            story_points=3,
        )


@pytest.mark.parametrize("points", [1, 2, 3, 5, 8, 13])
def test_story_points_accepts_fibonacci_values(points: int) -> None:
    story = UserStory(
        id=f"US-{points}",
        title="Valid points",
        as_a="user",
        i_want="a feature",
        so_that="I get value",
        source_requirement_ids=["REQ-001"],
        priority="must-have",
        story_points=points,
    )
    assert story.story_points == points


@pytest.mark.parametrize("points", [0, 4, 6, 21])
def test_story_points_rejects_non_fibonacci_values(points: int) -> None:
    with pytest.raises(ValidationError):
        UserStory(
            id=f"US-{points}",
            title="Invalid points",
            as_a="user",
            i_want="a feature",
            so_that="I get value",
            source_requirement_ids=["REQ-001"],
            priority="must-have",
            story_points=points,
        )


def test_captured_at_defaults_to_now() -> None:
    before = datetime.now(UTC)
    requirement = Requirement(text="Users can export reports", category="functional")
    after = datetime.now(UTC)
    assert before <= requirement.captured_at <= after


def test_discovery_session_aggregates_requirements_and_user_stories(
    sample_session: DiscoverySession,
) -> None:
    assert len(sample_session.requirements) == 2
    assert len(sample_session.user_stories) == 2
    assert sample_session.requirements[0].id == "REQ-001"
    assert sample_session.user_stories[0].id == "US-001"
