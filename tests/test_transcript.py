from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from realtime_assistant.main import create_transcript_writer, parse_args, send_text_message
from realtime_assistant.models import DiscoverySession
from realtime_assistant.tools import dispatch_tool
from realtime_assistant.transcript import TranscriptWriter


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, message: str) -> None:
        self.sent.append(message)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_transcript_writer_creates_text_and_jsonl_with_session_id(tmp_path: Path) -> None:
    session = DiscoverySession(session_id="DISC-TEST")
    started_at = datetime(2026, 6, 8, 14, 30, 5, tzinfo=UTC)

    writer = TranscriptWriter(session, output_dir=tmp_path, started_at=started_at)
    writer.record_user_message("Users need SSO.")
    writer.record_assistant_delta("What identity ")
    writer.record_assistant_delta("provider?")
    writer.flush_assistant_message()
    writer.record_tool_call(
        "capture_requirement",
        {"requirement": "SSO", "category": "functional"},
    )
    writer.record_tool_result("capture_requirement", {"ok": True})
    writer.close()

    assert writer.text_path == tmp_path / "2026-06-08_14-30-05_DISC-TEST.txt"
    assert writer.jsonl_path == tmp_path / "2026-06-08_14-30-05_DISC-TEST.jsonl"
    text = writer.text_path.read_text(encoding="utf-8")
    assert "Session ID: DISC-TEST" in text
    assert "User: Users need SSO." in text
    assert "Assistant: What identity provider?" in text
    assert "Tool Call: capture_requirement" in text
    assert '"category": "functional"' in text
    assert "Tool Result: capture_requirement" in text
    assert "Session End:" in text

    records = read_jsonl(writer.jsonl_path)
    assert [record["type"] for record in records] == [
        "session_started",
        "user_message",
        "assistant_message",
        "tool_call",
        "tool_result",
        "session_ended",
    ]
    assert {record["session_id"] for record in records} == {"DISC-TEST"}
    assert records[3]["name"] == "capture_requirement"
    assert records[3]["arguments"] == {"requirement": "SSO", "category": "functional"}
    assert records[4]["status"] == "ok"
    assert records[4]["result"] == {"ok": True}
    assert "ended_at" in records[5]


def test_send_text_message_records_user_message(tmp_path: Path) -> None:
    writer = TranscriptWriter(DiscoverySession(session_id="DISC-INPUT"), output_dir=tmp_path)
    websocket = FakeWebSocket()

    asyncio.run(send_text_message(websocket, "Capture reporting requirements.", writer))

    assert len(websocket.sent) == 2
    records = read_jsonl(writer.jsonl_path)
    assert records[1]["type"] == "user_message"
    assert records[1]["text"] == "Capture reporting requirements."


def test_dispatch_tool_records_call_and_result_with_mocked_handler(tmp_path: Path) -> None:
    async def handler(requirement: str, category: str) -> dict[str, str]:
        return {"captured": requirement, "category": category}

    writer = TranscriptWriter(DiscoverySession(session_id="DISC-TOOL"), output_dir=tmp_path)
    arguments = json.dumps({"requirement": "Export audit trail", "category": "functional"})

    with patch.dict("realtime_assistant.tools.FUNCTION_MAP", {"capture_requirement": handler}):
        result = asyncio.run(dispatch_tool("capture_requirement", arguments, writer))

    assert result == {"captured": "Export audit trail", "category": "functional"}
    records = read_jsonl(writer.jsonl_path)
    assert records[1]["type"] == "tool_call"
    assert records[1]["name"] == "capture_requirement"
    assert records[1]["arguments"] == {
        "requirement": "Export audit trail",
        "category": "functional",
    }
    assert records[2]["type"] == "tool_result"
    assert records[2]["status"] == "ok"
    assert records[2]["result"] == result


def test_no_transcript_flag_disables_transcript_creation(tmp_path: Path) -> None:
    with patch("sys.argv", ["raa", "--no-transcript"]):
        args = parse_args()

    assert args.no_transcript is True
    assert create_transcript_writer(enabled=not args.no_transcript, output_dir=tmp_path) is None
    assert list(tmp_path.iterdir()) == []
