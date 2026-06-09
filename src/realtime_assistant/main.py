from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SRC_DIR = SCRIPT_DIR.parent
if str(SCRIPT_DIR) in sys.path:
    sys.path.remove(str(SCRIPT_DIR))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import argparse
import asyncio
import base64
import contextlib
import json
import os
from typing import Any

import websockets
from dotenv import load_dotenv

from realtime_assistant.logging import console, logger
from realtime_assistant.memory import SESSIONS_DIR, SessionMemory, memory
from realtime_assistant.models import DiscoverySession
from realtime_assistant.prompts import SYSTEM_PROMPT, VOICE_MODE_INTRO
from realtime_assistant.tools import TOOL_SCHEMAS, dispatch_tool
from realtime_assistant.transcript import TranscriptWriter

REALTIME_MODEL = "gpt-4o-realtime-preview"
REALTIME_URL = f"wss://api.openai.com/v1/realtime?model={REALTIME_MODEL}"
REALTIME_RECONNECT_ATTEMPTS = 3
REALTIME_RECONNECT_INITIAL_DELAY = 1.0
REALTIME_RECONNECT_MAX_DELAY = 8.0

TRANSIENT_REALTIME_ERRORS = (
    websockets.ConnectionClosed,
    ConnectionError,
    EOFError,
    OSError,
    TimeoutError,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Realtime AI assistant for discovery calls.")
    parser.add_argument(
        "--prompts",
        help="Optional text prompts separated by | for scripted sessions.",
    )
    parser.add_argument(
        "--model",
        default=REALTIME_MODEL,
        help="Realtime model name.",
    )
    parser.add_argument(
        "--voice",
        action="store_true",
        help="Enable live microphone input (requires sounddevice).",
    )
    parser.add_argument(
        "--no-dashboard",
        action="store_true",
        help="Disable the web dashboard.",
    )
    parser.add_argument(
        "--dashboard-port",
        type=int,
        default=8000,
        help="Port for the web dashboard.",
    )
    parser.add_argument(
        "--reconnect-attempts",
        type=int,
        default=REALTIME_RECONNECT_ATTEMPTS,
        help="Number of times to retry a dropped Realtime WebSocket connection.",
    )
    parser.add_argument(
        "--reconnect-delay",
        type=float,
        default=REALTIME_RECONNECT_INITIAL_DELAY,
        help="Initial reconnect delay in seconds. Retries use bounded exponential backoff.",
    )
    parser.add_argument(
        "--reconnect-max-delay",
        type=float,
        default=REALTIME_RECONNECT_MAX_DELAY,
        help="Maximum reconnect delay in seconds.",
    )
    parser.add_argument(
        "--no-transcript",
        action="store_true",
        help="Disable writing conversation transcript files.",
    )
    parser.add_argument(
        "--resume",
        help="Load an existing discovery session from sessions/<session_id>.json.",
    )
    parser.add_argument(
        "--session-id",
        help="Start a new discovery session with a known session ID.",
    )
    args = parser.parse_args()
    if args.resume and args.session_id:
        parser.error("--resume and --session-id cannot be used together.")
    return args


def initialize_session_from_args(args: argparse.Namespace) -> DiscoverySession:
    if args.resume:
        session = memory.load_session(args.resume, SESSIONS_DIR)
        console.print(f"↩️  Resumed session: {session.session_id}")
        return session
    if args.session_id:
        session = memory.create_session(DiscoverySession(session_id=args.session_id))
        console.print(f"🧭 Session ID: {session.session_id}")
        return session
    return memory.get_current_session()


def create_transcript_writer(
    *,
    enabled: bool,
    output_dir: Path | str | None = None,
) -> TranscriptWriter | None:
    if not enabled:
        return None
    if output_dir is None:
        return TranscriptWriter(memory.get_current_session())
    return TranscriptWriter(memory.get_current_session(), output_dir=output_dir)


async def main() -> None:
    args = parse_args()
    initialize_session_from_args(args)

    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set. Copy .env.example to .env and add a key.")

    url = f"wss://api.openai.com/v1/realtime?model={args.model}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "OpenAI-Beta": "realtime=v1",
    }
    transcript = create_transcript_writer(enabled=not args.no_transcript)
    if transcript is not None:
        console.print(f"📝 Transcript: {transcript.text_path}")

    dashboard_task: asyncio.Task[None] | None = None
    if not args.no_dashboard:
        from realtime_assistant.server import start_dashboard

        dashboard_task = await start_dashboard(port=args.dashboard_port)
        console.print(f"📊 Dashboard running at http://localhost:{args.dashboard_port}")

    mic_stream = None
    if args.voice:
        from realtime_assistant.audio import MicrophoneStream

        mic_stream = MicrophoneStream()
        mic_stream.start()
        console.print("🎤 Voice mode active — speak now. Press Ctrl+C to end session.")
    else:
        console.print("💬 Text mode — type your message. Type quit to exit.")

    try:
        await run_realtime_session(
            url,
            headers,
            voice_mode=args.voice,
            scripted_prompts=args.prompts,
            mic_stream=mic_stream,
            reconnect_attempts=args.reconnect_attempts,
            reconnect_initial_delay=args.reconnect_delay,
            reconnect_max_delay=args.reconnect_max_delay,
            transcript=transcript,
        )
    finally:
        session_path = memory.save_session(SESSIONS_DIR)
        console.print(f"💾 Session saved: {session_path}")
        if transcript is not None:
            transcript.close()
        if dashboard_task is not None:
            dashboard_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await dashboard_task
        if mic_stream is not None:
            mic_stream.stop()


def connect_realtime(url: str, headers: dict[str, str]) -> Any:
    try:
        return websockets.connect(url, additional_headers=headers, max_size=None)
    except TypeError:
        return websockets.connect(url, extra_headers=headers, max_size=None)


async def configure_session(
    websocket: websockets.WebSocketClientProtocol,
    voice_mode: bool = False,
    create_response: bool = True,
) -> None:
    instructions = SYSTEM_PROMPT
    session: dict[str, Any] = {
        "modalities": ["text"],
        "instructions": instructions,
        "tool_choice": "auto",
        "tools": TOOL_SCHEMAS,
    }
    if voice_mode:
        instructions = f"{VOICE_MODE_INTRO}\n\n{SYSTEM_PROMPT}"
        session.update(
            {
                "modalities": ["text", "audio"],
                "instructions": instructions,
                "voice": "alloy",
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_transcription": {"model": "whisper-1"},
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 600,
                },
            }
        )

    await websocket.send(
        json.dumps(
            {
                "type": "session.update",
                "session": session,
            }
        )
    )
    if create_response:
        await websocket.send(json.dumps({"type": "response.create"}))


async def run_realtime_session(
    url: str,
    headers: dict[str, str],
    *,
    voice_mode: bool,
    scripted_prompts: str | None,
    mic_stream: Any = None,
    reconnect_attempts: int = REALTIME_RECONNECT_ATTEMPTS,
    reconnect_initial_delay: float = REALTIME_RECONNECT_INITIAL_DELAY,
    reconnect_max_delay: float = REALTIME_RECONNECT_MAX_DELAY,
    session_memory: SessionMemory = memory,
    transcript: TranscriptWriter | None = None,
) -> None:
    retries_used = 0
    max_delay = max(0.0, reconnect_max_delay)
    delay = min(max(0.0, reconnect_initial_delay), max_delay)

    try:
        while True:
            try:
                await run_single_realtime_connection(
                    url,
                    headers,
                    voice_mode=voice_mode,
                    scripted_prompts=scripted_prompts,
                    mic_stream=mic_stream,
                    session_memory=session_memory,
                    replay_context=retries_used > 0,
                    transcript=transcript,
                )
                if retries_used:
                    console.print("[green]Realtime connection restored.[/green]")
                return
            except asyncio.CancelledError:
                raise
            except TRANSIENT_REALTIME_ERRORS as exc:
                if retries_used >= reconnect_attempts:
                    console.print(
                        "[red]Realtime connection dropped and reconnect attempts are exhausted.[/red]"
                    )
                    logger.warning("Realtime WebSocket reconnect attempts exhausted: %s", exc)
                    raise

                retries_used += 1
                console.print(
                    "[yellow]Realtime connection dropped. "
                    f"Reconnecting ({retries_used}/{reconnect_attempts}) in {delay:.1f}s...[/yellow]"
                )
                logger.info("Realtime WebSocket dropped; retrying in %.1fs: %s", delay, exc)
                if delay > 0:
                    await asyncio.sleep(delay)
                delay = min(max_delay, delay * 2 if delay else reconnect_initial_delay or 0.0)
    finally:
        if transcript is not None:
            transcript.close()


async def run_single_realtime_connection(
    url: str,
    headers: dict[str, str],
    *,
    voice_mode: bool,
    scripted_prompts: str | None,
    mic_stream: Any = None,
    session_memory: SessionMemory = memory,
    replay_context: bool = False,
    transcript: TranscriptWriter | None = None,
) -> None:
    async with connect_realtime(url, headers) as websocket:
        await configure_session(websocket, voice_mode=voice_mode, create_response=False)
        if replay_context:
            await replay_session_context(websocket, session_memory)
        await websocket.send(json.dumps({"type": "response.create"}))
        console.print("[green]Realtime connection established.[/green]")
        logger.info("Realtime discovery session started. Type messages, or 'done' to generate stories.")

        receiver_task = asyncio.create_task(receive_events(websocket, transcript))
        if voice_mode:
            if mic_stream is None:
                raise RuntimeError("Voice mode requested but microphone stream was not initialized.")
            sender_task = asyncio.create_task(voice_sender(websocket, mic_stream))
        else:
            sender_task = asyncio.create_task(send_user_input(websocket, scripted_prompts, transcript))

        done, pending = await asyncio.wait(
            {receiver_task, sender_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

        for task in done:
            try:
                task.result()
            except asyncio.CancelledError:
                raise
            except TRANSIENT_REALTIME_ERRORS:
                raise

        if receiver_task in done and sender_task not in done:
            raise ConnectionError("Realtime WebSocket closed before the user session ended.")


async def replay_session_context(
    websocket: websockets.WebSocketClientProtocol,
    session_memory: SessionMemory = memory,
) -> None:
    context = build_session_context_message(session_memory.get_current_session())
    if context is None:
        return

    await websocket.send(
        json.dumps(
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": context}],
                },
            }
        )
    )
    console.print("[cyan]Replayed captured discovery context after reconnect.[/cyan]")


def build_session_context_message(session: DiscoverySession) -> str | None:
    if not session.requirements and not session.user_stories:
        return None

    lines = [
        "Session continuity context after a Realtime WebSocket reconnect.",
        "Use this as memory for the ongoing discovery conversation; do not treat it as a new user request.",
        f"Discovery session: {session.session_id}",
    ]

    if session.requirements:
        lines.append("Captured requirements:")
        for requirement in session.requirements:
            lines.append(f"- {requirement.id} [{requirement.category}]: {requirement.text}")

    if session.user_stories:
        lines.append("Generated user stories:")
        for story in session.user_stories:
            lines.append(
                f"- {story.id} ({story.priority}, {story.story_points} pts): "
                f"As a {story.as_a}, I want {story.i_want}, so that {story.so_that}."
            )

    return "\n".join(lines)


async def send_user_input(
    websocket: websockets.WebSocketClientProtocol,
    scripted_prompts: str | None,
    transcript: TranscriptWriter | None = None,
) -> None:
    if scripted_prompts:
        prompts = [prompt.strip() for prompt in scripted_prompts.split("|") if prompt.strip()]
        for prompt in prompts:
            await send_text_message(websocket, prompt, transcript)
            await asyncio.sleep(0.2)
        return

    while True:
        text = await asyncio.to_thread(input, "\nYou: ")
        if not text.strip():
            continue
        await send_text_message(websocket, text, transcript)
        if text.strip().lower() in {"quit", "exit"}:
            return


async def send_text_message(
    websocket: websockets.WebSocketClientProtocol,
    text: str,
    transcript: TranscriptWriter | None = None,
) -> None:
    if transcript is not None:
        transcript.record_user_message(text)
    await websocket.send(
        json.dumps(
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": text}],
                },
            }
        )
    )
    await websocket.send(json.dumps({"type": "response.create"}))


async def voice_sender(
    websocket: websockets.WebSocketClientProtocol,
    mic_stream: Any,
) -> None:
    async for chunk in mic_stream.chunks():
        audio = base64.b64encode(chunk).decode("ascii")
        await websocket.send(
            json.dumps(
                {
                    "type": "input_audio_buffer.append",
                    "audio": audio,
                }
            )
        )


async def receive_events(
    websocket: websockets.WebSocketClientProtocol,
    transcript: TranscriptWriter | None = None,
) -> None:
    async for raw_event in websocket:
        try:
            event = json.loads(raw_event)
        except json.JSONDecodeError:
            logger.warning("Ignoring malformed Realtime event: %r", raw_event)
            continue
        event_type = event.get("type", "")

        if event_type == "error":
            logger.error("Realtime API error: %s", event.get("error"))
            continue

        if event_type in {"response.text.delta", "response.output_text.delta"}:
            delta = event.get("delta", "")
            console.print(delta, end="")
            if transcript is not None:
                transcript.record_assistant_delta(delta)
            continue

        if event_type in {"response.text.done", "response.output_text.done"}:
            console.print()
            if transcript is not None:
                transcript.flush_assistant_message()
            continue

        if event_type == "response.audio_transcript.delta":
            delta = event.get("delta", "")
            console.print(delta, end="")
            if transcript is not None:
                transcript.record_assistant_delta(delta)
            continue

        if event_type == "response.audio_transcript.done":
            if transcript is not None:
                transcript.flush_assistant_message()
            continue

        if event_type == "conversation.item.input_audio_transcription.completed":
            if transcript is not None and event.get("transcript"):
                transcript.record_user_message(event["transcript"])
            continue

        if event_type == "response.function_call_arguments.done":
            await handle_function_call(websocket, event, transcript)
            continue

        if event_type == "response.done":
            if transcript is not None:
                transcript.flush_assistant_message()
            await handle_completed_response(websocket, event, transcript)


async def handle_completed_response(
    websocket: websockets.WebSocketClientProtocol,
    event: dict[str, Any],
    transcript: TranscriptWriter | None = None,
) -> None:
    response = event.get("response", {})
    for output in response.get("output", []):
        if output.get("type") == "function_call":
            await handle_function_call(websocket, output, transcript)


async def handle_function_call(
    websocket: websockets.WebSocketClientProtocol,
    event: dict[str, Any],
    transcript: TranscriptWriter | None = None,
) -> None:
    name = event.get("name")
    call_id = event.get("call_id")
    arguments = event.get("arguments")
    if not name or not call_id:
        return

    logger.info("Calling tool: %s", name)
    result = await dispatch_tool(name, arguments, transcript)
    await websocket.send(
        json.dumps(
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(result),
                },
            }
        )
    )
    await websocket.send(json.dumps({"type": "response.create"}))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Session stopped.")
