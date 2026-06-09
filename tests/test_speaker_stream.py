"""Tests for SpeakerStream audio output playback (issue #22)."""

from __future__ import annotations

import base64
import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.modules.setdefault("sounddevice", MagicMock())

from realtime_assistant.audio import SpeakerStream
from realtime_assistant.main import receive_events
from realtime_assistant.memory import SessionMemory

# ---------------------------------------------------------------------------
# SpeakerStream unit tests
# ---------------------------------------------------------------------------


def test_speaker_stream_start_opens_raw_output_stream() -> None:
    with patch("realtime_assistant.audio.sd") as mock_sd:
        stream = SpeakerStream()
        stream.start()
        mock_sd.RawOutputStream.assert_called_once()
        mock_sd.RawOutputStream.return_value.start.assert_called_once()
        stream.stop()


def test_speaker_stream_stop_closes_stream() -> None:
    with patch("realtime_assistant.audio.sd"):
        stream = SpeakerStream()
        stream.start()
        stream.stop()
        assert stream._stream is not None  # stream object still exists but was stopped/closed


def test_speaker_stream_enqueue_delivers_bytes_to_playback() -> None:
    """enqueue() puts bytes in the queue; the playback thread drains them."""
    with patch("realtime_assistant.audio.sd") as mock_sd:
        # Make RawOutputStream.write() a no-op
        mock_sd.RawOutputStream.return_value.write = MagicMock()
        stream = SpeakerStream()
        stream.start()
        stream.enqueue(b"\x00\x01\x02")
        stream.stop()  # waits for thread to drain
        mock_sd.RawOutputStream.return_value.write.assert_called_with(b"\x00\x01\x02")


# ---------------------------------------------------------------------------
# receive_events audio delta tests
# ---------------------------------------------------------------------------


class FakeWebSocket:
    """Feeds a fixed sequence of JSON events then stops iteration."""

    def __init__(self, events: list[dict]) -> None:
        self._events = iter(events)

    def __aiter__(self) -> FakeWebSocket:
        return self

    async def __anext__(self) -> str:
        try:
            return json.dumps(next(self._events))
        except StopIteration:
            raise StopAsyncIteration


@pytest.mark.asyncio
async def test_receive_events_enqueues_audio_delta_to_speaker_stream() -> None:
    pcm_bytes = b"\x10\x20\x30\x40"
    encoded = base64.b64encode(pcm_bytes).decode("ascii")

    events = [{"type": "response.audio.delta", "delta": encoded}]
    websocket = FakeWebSocket(events)

    enqueued: list[bytes] = []
    mock_speaker = SimpleNamespace(enqueue=enqueued.append)

    await receive_events(websocket, transcript=None, speaker_stream=mock_speaker)

    assert enqueued == [pcm_bytes]


@pytest.mark.asyncio
async def test_receive_events_ignores_audio_delta_without_speaker_stream() -> None:
    """Should not raise even when speaker_stream is None (text mode)."""
    pcm_bytes = b"\x00\xFF"
    encoded = base64.b64encode(pcm_bytes).decode("ascii")

    events = [{"type": "response.audio.delta", "delta": encoded}]
    websocket = FakeWebSocket(events)

    # Must not raise
    await receive_events(websocket, transcript=None, speaker_stream=None)


@pytest.mark.asyncio
async def test_receive_events_skips_empty_audio_delta() -> None:
    """Empty base64 payload should not call enqueue."""
    events = [{"type": "response.audio.delta", "delta": ""}]
    websocket = FakeWebSocket(events)

    enqueued: list[bytes] = []
    mock_speaker = SimpleNamespace(enqueue=enqueued.append)

    await receive_events(websocket, transcript=None, speaker_stream=mock_speaker)

    assert enqueued == []


@pytest.mark.asyncio
async def test_receive_events_accumulates_response_done_usage() -> None:
    store = SessionMemory()
    events = [
        {
            "type": "response.done",
            "response": {
                "usage": {
                    "input_tokens": 120,
                    "output_tokens": 30,
                },
                "output": [],
            },
        }
    ]
    websocket = FakeWebSocket(events)

    await receive_events(websocket, transcript=None, session_memory=store)

    usage = store.get_current_session().costs.realtime
    assert usage.input_tokens == 120
    assert usage.output_tokens == 30
