from __future__ import annotations

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
