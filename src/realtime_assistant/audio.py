"""Microphone capture and audio streaming for Voice Input Mode."""

from __future__ import annotations

import asyncio
import queue
import threading
from collections.abc import AsyncIterator
from typing import Any

SAMPLE_RATE = 24000
CHANNELS = 1
DTYPE = "int16"
CHUNK_MS = 100

sd: Any | None = None


def _compute_chunk_frames() -> int:
    return int(SAMPLE_RATE * CHUNK_MS / 1000)


class MicrophoneStream:
    """
    Captures microphone audio in a background thread and exposes
    an async generator of raw PCM bytes chunks.
    """

    def __init__(self) -> None:
        self._q: queue.Queue[bytes] = queue.Queue()
        self._stop_event = threading.Event()
        self._stream: Any | None = None

    def start(self) -> None:
        """Open the sounddevice input stream."""
        global sd
        if sd is None:
            import sounddevice as sounddevice_module

            sd = sounddevice_module

        chunk_frames = _compute_chunk_frames()
        self._stream = sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            blocksize=chunk_frames,
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._stream:
            self._stream.stop()
            self._stream.close()

    def _callback(self, indata: Any, frames: int, time: Any, status: Any) -> None:
        self._q.put(bytes(indata))

    async def chunks(self) -> AsyncIterator[bytes]:
        """Yield PCM chunks as they arrive from the mic."""
        loop = asyncio.get_event_loop()
        while not self._stop_event.is_set():
            try:
                chunk = await loop.run_in_executor(None, self._q.get, True, 0.2)
                yield chunk
            except queue.Empty:
                continue


class SpeakerStream:
    """
    Plays raw PCM audio from the Realtime API through the system speaker.

    Audio is fed via ``enqueue(pcm_bytes)`` from the async event loop and
    played in a background sounddevice output stream. The sounddevice module
    is imported lazily so text mode works without the package installed.
    """

    def __init__(self) -> None:
        self._q: queue.Queue[bytes | None] = queue.Queue()
        self._stream: Any | None = None

    def start(self) -> None:
        """Open the sounddevice output stream and begin playback."""
        global sd
        if sd is None:
            import sounddevice as sounddevice_module

            sd = sounddevice_module

        self._stream = sd.RawOutputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
        )
        self._stream.start()
        self._thread = threading.Thread(target=self._playback_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Signal the playback thread to finish and close the stream."""
        self._q.put(None)  # sentinel
        if hasattr(self, "_thread"):
            self._thread.join(timeout=2.0)
        if self._stream:
            self._stream.stop()
            self._stream.close()

    def enqueue(self, pcm_bytes: bytes) -> None:
        """Enqueue raw PCM bytes for playback. Safe to call from any thread."""
        self._q.put(pcm_bytes)

    def _playback_loop(self) -> None:
        while True:
            chunk = self._q.get()
            if chunk is None:
                break
            try:
                if self._stream:
                    self._stream.write(chunk)
            except Exception:
                pass
