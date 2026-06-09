from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from realtime_assistant.models import DiscoverySession

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRANSCRIPTS_DIR = PROJECT_ROOT / "transcripts"


class TranscriptWriter:
    """Persist a human and machine readable transcript for one discovery session."""

    def __init__(
        self,
        session: DiscoverySession,
        *,
        output_dir: Path | str = TRANSCRIPTS_DIR,
        started_at: datetime | None = None,
    ) -> None:
        self.session_id = session.session_id
        self.started_at = started_at or datetime.now(UTC)
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        filename = self.started_at.strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{filename}_{self.session_id}"
        self.text_path = output_path / f"{filename}.txt"
        self.jsonl_path = output_path / f"{filename}.jsonl"
        self._assistant_buffer: list[str] = []
        self._closed = False

        header = [
            "Conversation Transcript",
            f"Session ID: {self.session_id}",
            f"Started At: {self.started_at.isoformat()}",
            "",
        ]
        self.text_path.write_text("\n".join(header), encoding="utf-8")
        self.jsonl_path.write_text("", encoding="utf-8")
        self._write_jsonl(
            {
                "type": "session_started",
                "session_id": self.session_id,
                "started_at": self.started_at.isoformat(),
            }
        )

    def close(self) -> None:
        """Flush pending content and record session completion once."""
        if self._closed:
            return
        self.flush_assistant_message()
        ended_at = datetime.now(UTC).isoformat()
        self._append_text("Session End", ended_at)
        self._write_jsonl({"type": "session_ended", "ended_at": ended_at})
        self._closed = True

    def record_user_message(self, text: str) -> None:
        self.flush_assistant_message()
        self._append_text("User", text)
        self._write_jsonl({"type": "user_message", "text": text})

    def record_assistant_delta(self, delta: str) -> None:
        if delta:
            self._assistant_buffer.append(delta)

    def flush_assistant_message(self) -> None:
        if not self._assistant_buffer:
            return
        text = "".join(self._assistant_buffer)
        self._assistant_buffer.clear()
        self._append_text("Assistant", text)
        self._write_jsonl({"type": "assistant_message", "text": text})

    def record_tool_call(self, name: str, arguments: Any) -> None:
        self.flush_assistant_message()
        self._append_text("Tool Call", f"{name} {self._format_json(arguments)}")
        self._write_jsonl({"type": "tool_call", "name": name, "arguments": arguments})

    def record_tool_result(self, name: str, result: Any) -> None:
        self._append_text("Tool Result", f"{name} {self._format_json(result)}")
        status = self._result_status(result)
        self._write_jsonl(
            {"type": "tool_result", "name": name, "status": status, "result": result}
        )

    def _append_text(self, label: str, value: str) -> None:
        timestamp = datetime.now(UTC).isoformat()
        with self.text_path.open("a", encoding="utf-8") as file:
            file.write(f"[{timestamp}] {label}: {value}\n")

    def _write_jsonl(self, payload: dict[str, Any]) -> None:
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "session_id": self.session_id,
            **payload,
        }
        with self.jsonl_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, sort_keys=True) + "\n")

    @staticmethod
    def _format_json(value: Any) -> str:
        return json.dumps(value, indent=2, sort_keys=True)

    @staticmethod
    def _result_status(result: Any) -> str:
        if isinstance(result, dict) and result.get("ok") is False:
            return "error"
        return "ok"
