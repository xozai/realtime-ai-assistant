from __future__ import annotations

import asyncio
import json

from realtime_assistant.events import dashboard_event, event_bus, event_payload, format_sse
from realtime_assistant.memory import memory
from realtime_assistant.models import Requirement, UserStory


def setup_function() -> None:
    memory.reset_session()
    memory.configure_export_options()
    memory.clear_requirements()
    memory.clear_user_stories()
    memory.clear_clarified_topics()


def test_dashboard_event_payload_includes_type_and_session_snapshot(
    sample_requirement: Requirement,
    sample_user_story: UserStory,
) -> None:
    memory.add_requirement(sample_requirement)
    memory.set_user_stories([sample_user_story])

    event = dashboard_event("stories_generated", story_ids=[sample_user_story.id])
    payload = event_payload(event)

    assert payload["type"] == "stories_generated"
    assert payload["story_ids"] == ["US-001"]
    assert payload["snapshot"]["requirement_count"] == 1
    assert payload["snapshot"]["story_count"] == 1
    assert payload["snapshot"]["session_id"] == memory.get_current_session().session_id


def test_format_sse_serializes_json_data_line() -> None:
    event = dashboard_event("connected")

    frame = format_sse(event)

    assert frame.startswith("data: ")
    assert frame.endswith("\n\n")
    payload = json.loads(frame.removeprefix("data: ").strip())
    assert payload["type"] == "connected"
    assert "snapshot" in payload


def test_event_bus_delivers_published_events_to_subscriber() -> None:
    async def collect() -> str:
        async with event_bus.subscribe() as queue:
            await event_bus.publish("requirement_captured", requirement_id="REQ-001")
            event = await asyncio.wait_for(queue.get(), timeout=1)
            return event.type

    assert asyncio.run(collect()) == "requirement_captured"
