from __future__ import annotations

from realtime_assistant.memory import SessionMemory
from realtime_assistant.models import Requirement


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
