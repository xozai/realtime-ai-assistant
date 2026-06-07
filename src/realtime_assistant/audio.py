"""Microphone capture and audio streaming for Voice Input Mode."""

from __future__ import annotations

import asyncio
import queue
import threading
from typing import Any, AsyncIterator

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
