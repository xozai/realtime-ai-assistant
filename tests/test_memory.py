from __future__ import annotations

import pytest

from realtime_assistant import memory as memory_api
from realtime_assistant.memory import SessionMemory
from realtime_assistant.models import DiscoverySession, Requirement, UserStory


def test_add_requirement_stores_and_returns_requirement(sample_requirement: Requirement) -> None:
    store = SessionMemory()
    stored = store.add_requirement(sample_requirement)
    assert stored == sample_requirement
    assert store.get_all_requirements() == [sample_requirement]


def test_get_all_requirements_returns_all_stored_items(sample_requirement: Requirement) -> None:
    store = SessionMemory()
    second = Requirement(id="REQ-002", text="Users can reset passwords", category="functional")
    store.add_requirement(sample_requirement)
    store.add_requirement(second)
    assert store.get_all_requirements() == [sample_requirement, second]


def test_clear_requirements_empties_store(sample_requirement: Requirement) -> None:
    store = SessionMemory()
    store.add_requirement(sample_requirement)
    store.clear_requirements()
    assert store.get_all_requirements() == []


def test_duplicate_ids_are_overwritten(sample_requirement: Requirement) -> None:
    store = SessionMemory()
    replacement = Requirement(
        id=sample_requirement.id,
        text="Replacement text",
        category="constraint",
    )
    store.add_requirement(sample_requirement)
    store.add_requirement(replacement)
    assert store.get_all_requirements() == [replacement]


def test_session_lifecycle_returns_and_resets_current_session(
    sample_session: DiscoverySession,
) -> None:
    store = SessionMemory(sample_session)
    store.mark_clarified("Authentication")

    assert store.get_current_session() == sample_session
    assert store.dump_session()["session_id"] == "DISC-001"

    new_session = store.reset_session()

    assert new_session != sample_session
    assert store.list_requirements() == []
    assert store.list_user_stories() == []
    assert store.list_clarified_topics() == []


def test_requirement_crud_methods(sample_requirement: Requirement) -> None:
    store = SessionMemory()
    store.add_requirement(sample_requirement)

    updated = store.update_requirement(
        sample_requirement.id,
        text="Users can log in with SSO",
        category="constraint",
    )

    assert updated is not None
    assert store.get_requirement(sample_requirement.id) == updated
    assert updated.text == "Users can log in with SSO"
    assert updated.category == "constraint"
    assert store.remove_requirement(sample_requirement.id) is True
    assert store.remove_requirement(sample_requirement.id) is False


def test_user_story_crud_methods(sample_user_story: UserStory) -> None:
    store = SessionMemory()
    replacement = sample_user_story.model_copy(update={"title": "Updated login"})

    assert store.add_user_story(sample_user_story) == sample_user_story
    assert store.add_user_story(replacement) == replacement
    assert store.list_user_stories() == [replacement]
    assert store.get_user_story(sample_user_story.id) == replacement
    assert store.remove_user_story(sample_user_story.id) is True
    assert store.get_user_story(sample_user_story.id) is None


def test_get_all_user_stories_returns_all_stored_items(sample_user_story: UserStory) -> None:
    store = SessionMemory()
    second = sample_user_story.model_copy(update={"id": "US-002", "title": "Password reset"})

    store.add_user_story(sample_user_story)
    store.add_user_story(second)

    assert store.get_all_user_stories() == [sample_user_story, second]


def test_update_user_story_preserves_order_and_validates(sample_user_story: UserStory) -> None:
    store = SessionMemory()
    second = sample_user_story.model_copy(update={"id": "US-002", "title": "Password reset"})
    store.set_user_stories([sample_user_story, second])

    updated = store.update_user_story(
        sample_user_story.id,
        title="Updated email login",
        acceptance_criteria=["Given valid credentials, then access is granted."],
        priority="should-have",
        story_points=5,
    )

    assert updated is not None
    assert updated.title == "Updated email login"
    assert updated.acceptance_criteria == ["Given valid credentials, then access is granted."]
    assert updated.priority == "should-have"
    assert updated.story_points == 5
    assert store.list_user_stories() == [updated, second]
    assert store.update_user_story("missing", title="No-op") is None
    with pytest.raises(ValueError, match="story_points"):
        store.update_user_story(sample_user_story.id, story_points=4)


def test_replace_user_story_replaces_only_target_and_records_history(
    sample_user_story: UserStory,
) -> None:
    store = SessionMemory()
    second = sample_user_story.model_copy(update={"id": "US-002", "title": "Password reset"})
    replacement = sample_user_story.model_copy(
        update={"id": "US-NEW", "title": "Refined email login"}
    )
    store.set_user_stories([sample_user_story, second])

    updated = store.replace_user_story(
        sample_user_story.id,
        replacement,
        feedback="Make criteria testable",
        requirement_ids=["REQ-001"],
    )

    assert updated is not None
    assert updated.id == sample_user_story.id
    assert updated.title == "Refined email login"
    assert store.list_user_stories() == [updated, second]
    assert len(store.get_current_session().story_refinement_history) == 1
    history = store.get_current_session().story_refinement_history[0]
    assert history.previous_story == sample_user_story
    assert history.replacement_story == updated
    assert history.feedback == "Make criteria testable"
    assert history.requirement_ids == ["REQ-001"]
    assert store.replace_user_story("missing", replacement) is None


def test_replace_and_clear_user_stories(sample_user_story: UserStory) -> None:
    store = SessionMemory()

    store.replace_user_stories([sample_user_story])
    assert store.list_user_stories() == [sample_user_story]

    store.clear_user_stories()
    assert store.list_user_stories() == []


def test_clarified_topic_management() -> None:
    store = SessionMemory()

    normalized = store.mark_clarified("  Authentication  ")

    assert normalized == "authentication"
    assert store.is_topic_clarified("AUTHENTICATION") is True
    assert store.list_clarified_topics() == ["authentication"]
    assert store.remove_clarified_topic("authentication") is True
    assert store.remove_clarified_topic("authentication") is False


def test_cost_accumulation_updates_session_totals() -> None:
    store = SessionMemory()

    store.accumulate_realtime_usage(1000, 500)
    store.accumulate_chat_usage(2000, 1000)
    store.accumulate_embedding_usage(3000)
    store.accumulate_realtime_usage(250, 125)

    costs = store.get_current_session().costs
    assert costs.realtime.input_tokens == 1250
    assert costs.realtime.output_tokens == 625
    assert costs.realtime.total_tokens == 1875
    assert costs.realtime.estimated_cost_usd == pytest.approx(0.01875)
    assert costs.chat_completions.estimated_cost_usd == pytest.approx(0.015)
    assert costs.embeddings.estimated_cost_usd == pytest.approx(0.00006)
    assert costs.total_cost_usd == pytest.approx(0.03381)


def test_module_level_session_wrappers_expose_singleton_api(
    sample_requirement: Requirement,
    sample_user_story: UserStory,
) -> None:
    session = DiscoverySession(session_id="DISC-WRAPPER")

    assert memory_api.create_session(session) == session
    assert memory_api.get_current_session() == session
    assert memory_api.add_requirement(sample_requirement) == sample_requirement
    assert memory_api.get_all_requirements() == [sample_requirement]
    assert memory_api.update_requirement(sample_requirement.id, text="Updated requirement") is not None
    assert memory_api.get_requirement(sample_requirement.id).text == "Updated requirement"
    assert memory_api.add_user_story(sample_user_story) == sample_user_story
    assert memory_api.get_all_user_stories() == [sample_user_story]
    assert memory_api.update_user_story(sample_user_story.id, title="Updated story") is not None
    assert memory_api.get_user_story(sample_user_story.id).title == "Updated story"
    assert memory_api.remove_requirement(sample_requirement.id) is True
    assert memory_api.remove_user_story(sample_user_story.id) is True

    reset = memory_api.reset_session()

    assert reset != session
    assert memory_api.list_requirements() == []
    assert memory_api.list_user_stories() == []
