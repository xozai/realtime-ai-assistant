from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

sys.modules["sounddevice"] = MagicMock()

from realtime_assistant.audio import CHANNELS, CHUNK_MS, SAMPLE_RATE, MicrophoneStream


def test_constants_are_correct() -> None:
    assert SAMPLE_RATE == 24000
    assert CHANNELS == 1
    assert CHUNK_MS == 100


def test_microphone_stream_start_opens_stream() -> None:
    with patch("realtime_assistant.audio.sd") as mock_sd:
        stream = MicrophoneStream()
        stream.start()
        mock_sd.RawInputStream.assert_called_once()
        mock_sd.RawInputStream.return_value.start.assert_called_once()


def test_microphone_stream_stop_closes_stream() -> None:
    with patch("realtime_assistant.audio.sd"):
        stream = MicrophoneStream()
        stream.start()
        stream.stop()
        assert stream._stop_event.is_set()


def test_callback_puts_bytes_in_queue() -> None:
    stream = MicrophoneStream()
    stream._callback(b"audio_data", 100, None, None)
    assert not stream._q.empty()
    assert stream._q.get() == b"audio_data"
