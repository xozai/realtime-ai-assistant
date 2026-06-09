from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
import websockets

from realtime_assistant import main
from realtime_assistant.memory import SessionMemory
from realtime_assistant.models import DiscoverySession, Requirement, UserStory


class FakeWebSocket:
    def __init__(self, *, close_on_receive: bool = False) -> None:
        self.close_on_receive = close_on_receive
        self.sent: list[str] = []

    async def send(self, message: str) -> None:
        self.sent.append(message)

    def __aiter__(self) -> FakeWebSocket:
        return self

    async def __anext__(self) -> str:
        if self.close_on_receive:
            raise websockets.ConnectionClosedError(None, None)
        await asyncio.Future()
        raise StopAsyncIteration


class FakeConnection:
    def __init__(self, websocket: FakeWebSocket) -> None:
        self.websocket = websocket

    async def __aenter__(self) -> FakeWebSocket:
        return self.websocket

    async def __aexit__(self, *exc_info: object) -> None:
        return None


def populated_memory() -> SessionMemory:
    session = DiscoverySession(
        session_id="DISC-RECONNECT",
        requirements=[
            Requirement(
                id="REQ-001",
                text="Users can continue discovery after a network drop",
                category="non-functional",
            )
        ],
        user_stories=[
            UserStory(
                id="US-001",
                title="Reconnect live discovery session",
                as_a="facilitator",
                i_want="the assistant to reconnect automatically",
                so_that="captured requirements remain available",
                acceptance_criteria=["Given a dropped socket, then the session reconnects."],
                priority="must-have",
                story_points=3,
            )
        ],
    )
    return SessionMemory(session)


@pytest.mark.asyncio
async def test_realtime_session_reconnects_and_replays_context(monkeypatch: pytest.MonkeyPatch) -> None:
    first_websocket = FakeWebSocket(close_on_receive=True)
    second_websocket = FakeWebSocket()
    sockets = [first_websocket, second_websocket]
    console_messages: list[str] = []

    def fake_connect_realtime(url: str, headers: dict[str, str]) -> FakeConnection:
        assert url == "wss://example.test/realtime"
        assert headers == {"Authorization": "Bearer test"}
        return FakeConnection(sockets.pop(0))

    async def fake_send_user_input(
        websocket: FakeWebSocket,
        scripted_prompts: str | None,
        transcript: object | None = None,
    ) -> None:
        assert transcript is None
        if websocket.close_on_receive:
            await asyncio.Future()

    monkeypatch.setattr(main, "connect_realtime", fake_connect_realtime)
    monkeypatch.setattr(main, "send_user_input", fake_send_user_input)
    monkeypatch.setattr(main, "console", SimpleNamespace(print=console_messages.append))

    await main.run_realtime_session(
        "wss://example.test/realtime",
        {"Authorization": "Bearer test"},
        voice_mode=False,
        scripted_prompts=None,
        reconnect_attempts=1,
        reconnect_initial_delay=0,
        session_memory=populated_memory(),
    )

    first_message = json.loads(first_websocket.sent[0])
    second_messages = [json.loads(message) for message in second_websocket.sent]
    second_session_update = second_messages[0]
    replay_message = second_messages[1]

    assert first_message["type"] == "session.update"
    assert second_session_update["type"] == "session.update"
    assert replay_message["type"] == "conversation.item.create"
    replay_text = replay_message["item"]["content"][0]["text"]
    assert "DISC-RECONNECT" in replay_text
    assert "REQ-001 [non-functional]" in replay_text
    assert "US-001" in replay_text
    assert second_messages[2] == {"type": "response.create"}
    assert any("Realtime connection dropped" in message for message in console_messages)
    assert any("Replayed captured discovery context" in message for message in console_messages)
    assert any("Realtime connection restored" in message for message in console_messages)


@pytest.mark.asyncio
async def test_realtime_session_gives_up_after_reconnect_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sockets = [FakeWebSocket(close_on_receive=True), FakeWebSocket(close_on_receive=True)]
    console_messages: list[str] = []

    monkeypatch.setattr(
        main,
        "connect_realtime",
        lambda _url, _headers: FakeConnection(sockets.pop(0)),
    )

    async def never_finishes(
        _websocket: FakeWebSocket,
        _scripted_prompts: str | None,
        _transcript: object | None = None,
    ) -> None:
        await asyncio.Future()

    monkeypatch.setattr(
        main,
        "send_user_input",
        never_finishes,
    )
    monkeypatch.setattr(main, "console", SimpleNamespace(print=console_messages.append))

    with pytest.raises(websockets.ConnectionClosedError):
        await main.run_realtime_session(
            "wss://example.test/realtime",
            {"Authorization": "Bearer test"},
            voice_mode=False,
            scripted_prompts=None,
            reconnect_attempts=1,
            reconnect_initial_delay=0,
            session_memory=populated_memory(),
        )

    assert any("Reconnect" in message or "Reconnecting" in message for message in console_messages)
    assert any("attempts are exhausted" in message for message in console_messages)


@pytest.mark.asyncio
async def test_realtime_session_uses_bounded_exponential_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0
    sleeps: list[float] = []

    async def always_drops(*_args: object, **_kwargs: object) -> None:
        nonlocal attempts
        attempts += 1
        raise ConnectionError("temporary network drop")

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(main, "run_single_realtime_connection", always_drops)
    monkeypatch.setattr(main.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(main, "console", SimpleNamespace(print=lambda *_args, **_kwargs: None))

    with pytest.raises(ConnectionError):
        await main.run_realtime_session(
            "wss://example.test/realtime",
            {"Authorization": "Bearer test"},
            voice_mode=False,
            scripted_prompts=None,
            reconnect_attempts=3,
            reconnect_initial_delay=1.0,
            reconnect_max_delay=2.5,
            session_memory=populated_memory(),
        )

    assert attempts == 4
    assert sleeps == [1.0, 2.0, 2.5]
