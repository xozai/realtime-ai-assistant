from __future__ import annotations

import asyncio
from unittest.mock import patch

from realtime_assistant.memory import memory
from realtime_assistant.models import Requirement
from realtime_assistant.tools import capture_requirement, dedupe_requirements


def setup_function() -> None:
    memory.reset_session()
    memory.configure_export_options()
    memory.clear_requirements()
    memory.clear_user_stories()
    memory.clear_clarified_topics()


def test_capture_requirement_skips_clear_duplicate() -> None:
    with (
        patch(
            "realtime_assistant.tools.llm.get_embedding",
            side_effect=[[1.0, 0.0, 0.0], [0.99, 0.1, 0.0]],
        ),
        patch("realtime_assistant.llm.score_requirement_confidence", return_value="medium"),
    ):
        first = asyncio.run(
            capture_requirement("Users can log in with email", "functional")
        )
        second = asyncio.run(
            capture_requirement("Users can authenticate using email", "functional")
        )

    assert first["ok"] is True
    assert second["ok"] is True
    assert second["skipped"] is True
    assert second["merged"] is True
    assert second["existing_requirement_id"] == first["requirement"]["id"]
    assert second["requirement_count"] == 1
    assert len(memory.list_requirements()) == 1


def test_capture_requirement_stores_clearly_distinct_pair() -> None:
    with (
        patch(
            "realtime_assistant.tools.llm.get_embedding",
            side_effect=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        ),
        patch("realtime_assistant.llm.score_requirement_confidence", return_value="high"),
    ):
        first = asyncio.run(
            capture_requirement("Users can log in with email", "functional")
        )
        second = asyncio.run(
            capture_requirement("Reports can be exported as CSV", "functional")
        )

    assert first["skipped"] is False
    assert second["skipped"] is False
    assert second["requirement_count"] == 2
    assert [req.text for req in memory.list_requirements()] == [
        "Users can log in with email",
        "Reports can be exported as CSV",
    ]


def test_dedupe_requirements_detects_near_duplicate_pair() -> None:
    first = Requirement(
        id="REQ-001",
        text="Users can log in with email",
        category="functional",
        embedding=[1.0, 0.0, 0.0],
    )
    second = Requirement(
        id="REQ-002",
        text="Users can authenticate using email",
        category="functional",
        embedding=[0.99, 0.1, 0.0],
    )
    distinct = Requirement(
        id="REQ-003",
        text="Reports can be exported as CSV",
        category="functional",
        embedding=[0.0, 1.0, 0.0],
    )
    memory.add_requirement(first)
    memory.add_requirement(second)
    memory.add_requirement(distinct)

    result = asyncio.run(dedupe_requirements())

    assert result["ok"] is True
    assert result["duplicate_pair_count"] == 1
    assert result["duplicate_pairs"][0]["requirement_id"] == "REQ-001"
    assert result["duplicate_pairs"][0]["similar_requirement_id"] == "REQ-002"
    assert result["duplicate_pairs"][0]["similarity"] >= 0.85
