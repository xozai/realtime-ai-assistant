from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from realtime_assistant.memory import memory


@dataclass(frozen=True)
class DashboardEvent:
    """A dashboard-visible state change ready for SSE serialization."""

    type: str
    snapshot: dict[str, Any]
    data: dict[str, Any]


class DashboardEventBus:
    """In-process pub/sub for the single-process dashboard server."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[DashboardEvent]] = set()

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[DashboardEvent]]:
        queue: asyncio.Queue[DashboardEvent] = asyncio.Queue(maxsize=20)
        self._subscribers.add(queue)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)

    async def publish(self, event_type: str, **data: Any) -> DashboardEvent:
        event = dashboard_event(event_type, **data)
        stale_subscribers: list[asyncio.Queue[DashboardEvent]] = []
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                stale_subscribers.append(queue)
        for queue in stale_subscribers:
            self._subscribers.discard(queue)
        return event


def session_snapshot() -> dict[str, Any]:
    session = memory.get_current_session()
    return {
        "session_id": session.session_id,
        "project_key": session.project_key,
        "project_name": session.project_name,
        "requirement_count": len(memory.list_requirements()),
        "story_count": len(memory.list_user_stories()),
        "refinement_count": len(session.story_refinement_history),
    }


def dashboard_event(event_type: str, **data: Any) -> DashboardEvent:
    return DashboardEvent(type=event_type, snapshot=session_snapshot(), data=data)


def event_payload(event: DashboardEvent) -> dict[str, Any]:
    return {
        "type": event.type,
        "snapshot": event.snapshot,
        **event.data,
    }


def format_sse(event: DashboardEvent) -> str:
    payload = json.dumps(event_payload(event), sort_keys=True)
    return f"data: {payload}\n\n"


event_bus = DashboardEventBus()
