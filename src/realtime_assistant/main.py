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
import json
import os
from typing import Any

import websockets
from dotenv import load_dotenv

from realtime_assistant.logging import console, logger
from realtime_assistant.prompts import SYSTEM_PROMPT, VOICE_MODE_INTRO
from realtime_assistant.tools import TOOL_SCHEMAS, dispatch_tool

REALTIME_MODEL = "gpt-4o-realtime-preview"
REALTIME_URL = f"wss://api.openai.com/v1/realtime?model={REALTIME_MODEL}"


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
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set. Copy .env.example to .env and add a key.")

    url = f"wss://api.openai.com/v1/realtime?model={args.model}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "OpenAI-Beta": "realtime=v1",
    }

    mic_stream = None
    if args.voice:
        from realtime_assistant.audio import MicrophoneStream

        mic_stream = MicrophoneStream()
        mic_stream.start()
        console.print("🎤 Voice mode active — speak now. Press Ctrl+C to end session.")
    else:
        console.print("💬 Text mode — type your message. Type quit to exit.")

    try:
        async with connect_realtime(url, headers) as websocket:
            await configure_session(websocket, voice_mode=args.voice)
            logger.info("Realtime discovery session started. Type messages, or 'done' to generate stories.")

            receiver_task = asyncio.create_task(receive_events(websocket))
            if args.voice:
                if mic_stream is None:
                    raise RuntimeError("Voice mode requested but microphone stream was not initialized.")
                sender_task = asyncio.create_task(voice_sender(websocket, mic_stream))
            else:
                sender_task = asyncio.create_task(send_user_input(websocket, args.prompts))

            done, pending = await asyncio.wait(
                {receiver_task, sender_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                task.result()
    finally:
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
    await websocket.send(json.dumps({"type": "response.create"}))


async def send_user_input(
    websocket: websockets.WebSocketClientProtocol,
    scripted_prompts: str | None,
) -> None:
    if scripted_prompts:
        prompts = [prompt.strip() for prompt in scripted_prompts.split("|") if prompt.strip()]
        for prompt in prompts:
            await send_text_message(websocket, prompt)
            await asyncio.sleep(0.2)
        return

    while True:
        text = await asyncio.to_thread(input, "\nYou: ")
        if not text.strip():
            continue
        await send_text_message(websocket, text)
        if text.strip().lower() in {"quit", "exit"}:
            return


async def send_text_message(websocket: websockets.WebSocketClientProtocol, text: str) -> None:
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


async def receive_events(websocket: websockets.WebSocketClientProtocol) -> None:
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
            console.print(event.get("delta", ""), end="")
            continue

        if event_type in {"response.text.done", "response.output_text.done"}:
            console.print()
            continue

        if event_type == "response.audio_transcript.delta":
            console.print(event.get("delta", ""), end="")
            continue

        if event_type == "response.function_call_arguments.done":
            await handle_function_call(websocket, event)
            continue

        if event_type == "response.done":
            await handle_completed_response(websocket, event)


async def handle_completed_response(
    websocket: websockets.WebSocketClientProtocol,
    event: dict[str, Any],
) -> None:
    response = event.get("response", {})
    for output in response.get("output", []):
        if output.get("type") == "function_call":
            await handle_function_call(websocket, output)


async def handle_function_call(
    websocket: websockets.WebSocketClientProtocol,
    event: dict[str, Any],
) -> None:
    name = event.get("name")
    call_id = event.get("call_id")
    arguments = event.get("arguments")
    if not name or not call_id:
        return

    logger.info("Calling tool: %s", name)
    result = await dispatch_tool(name, arguments)
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
