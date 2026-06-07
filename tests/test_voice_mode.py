from __future__ import annotations

import json

import pytest

from realtime_assistant.main import configure_session, voice_sender
from realtime_assistant.prompts import VOICE_MODE_INTRO


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, message: str) -> None:
        self.sent.append(message)


class FakeMicStream:
    async def chunks(self):
        yield b"audio_data"


@pytest.mark.asyncio
async def test_configure_session_text_mode_uses_text_only_modalities() -> None:
    websocket = FakeWebSocket()

    await configure_session(websocket)

    session_update = json.loads(websocket.sent[0])
    assert session_update["session"]["modalities"] == ["text"]
    assert "input_audio_format" not in session_update["session"]
    assert websocket.sent[1] == json.dumps({"type": "response.create"})


@pytest.mark.asyncio
async def test_configure_session_voice_mode_adds_audio_settings_and_intro() -> None:
    websocket = FakeWebSocket()

    await configure_session(websocket, voice_mode=True)

    session = json.loads(websocket.sent[0])["session"]
    assert session["modalities"] == ["text", "audio"]
    assert session["voice"] == "alloy"
    assert session["input_audio_format"] == "pcm16"
    assert session["output_audio_format"] == "pcm16"
    assert session["input_audio_transcription"] == {"model": "whisper-1"}
    assert session["turn_detection"]["type"] == "server_vad"
    assert session["instructions"].startswith(VOICE_MODE_INTRO)


@pytest.mark.asyncio
async def test_voice_sender_base64_encodes_pcm_chunks() -> None:
    websocket = FakeWebSocket()

    await voice_sender(websocket, FakeMicStream())

    message = json.loads(websocket.sent[0])
    assert message == {
        "type": "input_audio_buffer.append",
        "audio": "YXVkaW9fZGF0YQ==",
    }
