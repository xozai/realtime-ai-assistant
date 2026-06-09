from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from realtime_assistant import main
from realtime_assistant.memory import SessionMemory, memory
from realtime_assistant.models import DiscoverySession, Requirement


def setup_function() -> None:
    memory.reset_session()


def test_round_trip_save_load_session_and_clarified_topics(
    tmp_path: Path,
    sample_session: DiscoverySession,
) -> None:
    store = SessionMemory(sample_session)
    store.mark_clarified("Authentication")
    store.mark_clarified(" Reporting ")

    saved_path = store.save_session(tmp_path)

    payload = json.loads(saved_path.read_text(encoding="utf-8"))
    assert set(payload) == {"clarified_topics", "session"}
    assert payload["clarified_topics"] == ["authentication", "reporting"]
    assert payload["session"]["session_id"] == "DISC-001"
    assert payload["session"]["project_key"] == "default"
    assert saved_path == tmp_path / "default" / "DISC-001.json"

    loaded_store = SessionMemory()
    loaded = loaded_store.load_session("DISC-001", tmp_path)

    assert loaded == sample_session
    assert loaded_store.list_clarified_topics() == ["authentication", "reporting"]


def test_load_session_by_id_from_sessions_directory(
    tmp_path: Path,
    sample_session: DiscoverySession,
) -> None:
    SessionMemory(sample_session).save_session(tmp_path)

    loaded_store = SessionMemory()
    loaded = loaded_store.load_session("DISC-001", tmp_path)

    assert loaded.session_id == "DISC-001"
    assert [requirement.id for requirement in loaded.requirements] == ["REQ-001", "REQ-002"]


def test_session_persists_under_project_path(
    tmp_path: Path,
    sample_session: DiscoverySession,
) -> None:
    session = sample_session.model_copy(update={"project_key": "billing"})
    saved_path = SessionMemory(session).save_session(tmp_path)

    assert saved_path == tmp_path / "billing" / "DISC-001.json"
    assert not (tmp_path / "DISC-001.json").exists()


def test_load_session_falls_back_to_legacy_flat_path(
    tmp_path: Path,
    sample_session: DiscoverySession,
) -> None:
    legacy_path = tmp_path / "DISC-001.json"
    legacy_path.write_text(
        json.dumps(
            {
                "session": sample_session.model_dump(mode="json"),
                "clarified_topics": ["authentication"],
            }
        ),
        encoding="utf-8",
    )

    loaded_store = SessionMemory(project_key="billing")
    loaded = loaded_store.load_session("DISC-001", tmp_path, project_key="billing")

    assert loaded.session_id == "DISC-001"
    assert loaded.project_key == "billing"
    assert loaded_store.list_clarified_topics() == ["authentication"]


def test_session_resume_is_scoped_to_project(tmp_path: Path) -> None:
    billing = DiscoverySession(
        session_id="DISC-SHARED",
        project_key="billing",
        requirements=[
            Requirement(id="REQ-BILL", text="Billing exports invoices", category="functional")
        ],
    )
    support = DiscoverySession(
        session_id="DISC-SHARED",
        project_key="support",
        requirements=[
            Requirement(id="REQ-SUP", text="Support triages tickets", category="functional")
        ],
    )
    SessionMemory(billing).save_session(tmp_path)
    SessionMemory(support).save_session(tmp_path)

    loaded = SessionMemory().load_session("DISC-SHARED", tmp_path, project_key="support")

    assert loaded.project_key == "support"
    assert [req.id for req in loaded.requirements] == ["REQ-SUP"]


def test_new_session_memory_project_switch_does_not_bleed_requirements() -> None:
    billing_store = SessionMemory(project_key="billing")
    billing_store.add_requirement(
        Requirement(id="REQ-BILL", text="Billing exports invoices", category="functional")
    )

    support_store = SessionMemory(project_key="support")

    assert billing_store.get_current_session().project_key == "billing"
    assert support_store.get_current_session().project_key == "support"
    assert [req.id for req in billing_store.list_requirements()] == ["REQ-BILL"]
    assert support_store.list_requirements() == []


def test_append_after_resume_preserves_existing_requirements(
    tmp_path: Path,
    sample_session: DiscoverySession,
) -> None:
    SessionMemory(sample_session).save_session(tmp_path)
    resumed_store = SessionMemory()
    resumed_store.load_session("DISC-001", tmp_path)

    new_requirement = Requirement(
        id="REQ-003",
        text="Admins can export audit logs",
        category="functional",
    )
    resumed_store.add_requirement(new_requirement)

    assert [requirement.id for requirement in resumed_store.list_requirements()] == [
        "REQ-001",
        "REQ-002",
        "REQ-003",
    ]


@pytest.mark.asyncio
async def test_resume_hydrates_memory_before_transcript_dashboard_and_autosaves(
    tmp_path: Path,
    sample_session: DiscoverySession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    SessionMemory(sample_session).save_session(tmp_path)
    observed: dict[str, object] = {}

    class FakeTranscript:
        text_path = tmp_path / "transcript.txt"

        def close(self) -> None:
            observed["transcript_closed_session"] = memory.get_current_session().session_id

    def fake_create_transcript_writer(*, enabled: bool, output_dir: Path | str | None = None):
        assert enabled is True
        assert output_dir is None
        observed["transcript_session"] = memory.get_current_session().session_id
        observed["transcript_requirement_count"] = len(memory.list_requirements())
        return FakeTranscript()

    async def fake_start_dashboard(*, port: int):
        observed["dashboard_port"] = port
        observed["dashboard_session"] = memory.get_current_session().session_id
        observed["dashboard_requirement_count"] = len(memory.list_requirements())

        async def wait_forever() -> None:
            await asyncio.Future()

        return asyncio.create_task(wait_forever())

    async def fake_run_realtime_session(*_args: object, **kwargs: object) -> None:
        observed["run_session"] = memory.get_current_session().session_id
        observed["run_requirement_count"] = len(memory.list_requirements())
        observed["transcript_passed"] = kwargs["transcript"]
        memory.add_requirement(
            Requirement(
                id="REQ-003",
                text="Managers can view resumed-session reporting",
                category="functional",
            )
        )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(main, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(main, "create_transcript_writer", fake_create_transcript_writer)
    monkeypatch.setattr(main, "run_realtime_session", fake_run_realtime_session)

    import realtime_assistant.server as server

    monkeypatch.setattr(server, "start_dashboard", fake_start_dashboard)
    monkeypatch.setattr(
        "sys.argv",
        ["raa", "--resume", "DISC-001", "--dashboard-port", "8765"],
    )
    monkeypatch.setattr(main, "console", SimpleNamespace(print=lambda *_args, **_kwargs: None))

    await main.main()

    assert observed["transcript_session"] == "DISC-001"
    assert observed["dashboard_session"] == "DISC-001"
    assert observed["run_session"] == "DISC-001"
    assert observed["transcript_requirement_count"] == 2
    assert observed["dashboard_requirement_count"] == 2
    assert observed["run_requirement_count"] == 2
    assert observed["dashboard_port"] == 8765
    assert isinstance(observed["transcript_passed"], FakeTranscript)
    assert observed["transcript_closed_session"] == "DISC-001"

    saved = json.loads((tmp_path / "default" / "DISC-001.json").read_text(encoding="utf-8"))
    assert [req["id"] for req in saved["session"]["requirements"]] == [
        "REQ-001",
        "REQ-002",
        "REQ-003",
    ]


@pytest.mark.asyncio
async def test_project_flag_sets_session_and_scopes_autosave(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    async def fake_run_realtime_session(*_args: object, **_kwargs: object) -> None:
        session = memory.get_current_session()
        observed["project_key"] = session.project_key
        memory.add_requirement(
            Requirement(id="REQ-API", text="API keys can rotate", category="functional")
        )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(main, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(main, "run_realtime_session", fake_run_realtime_session)
    monkeypatch.setattr(
        "sys.argv",
        [
            "raa",
            "--project",
            "platform",
            "--session-id",
            "DISC-PROJ",
            "--no-dashboard",
            "--no-transcript",
        ],
    )
    monkeypatch.setattr(main, "console", SimpleNamespace(print=lambda *_args, **_kwargs: None))

    await main.main()

    saved = json.loads((tmp_path / "platform" / "DISC-PROJ.json").read_text(encoding="utf-8"))
    assert observed["project_key"] == "platform"
    assert saved["session"]["project_key"] == "platform"
    assert [req["id"] for req in saved["session"]["requirements"]] == ["REQ-API"]


@pytest.mark.asyncio
async def test_resume_uses_project_flag_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    billing = DiscoverySession(session_id="DISC-001", project_key="billing")
    support = DiscoverySession(
        session_id="DISC-001",
        project_key="support",
        requirements=[
            Requirement(id="REQ-SUP", text="Support triages tickets", category="functional")
        ],
    )
    SessionMemory(billing).save_session(tmp_path)
    SessionMemory(support).save_session(tmp_path)
    observed: dict[str, object] = {}

    async def fake_run_realtime_session(*_args: object, **_kwargs: object) -> None:
        session = memory.get_current_session()
        observed["project_key"] = session.project_key
        observed["requirements"] = [req.id for req in memory.list_requirements()]

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(main, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(main, "run_realtime_session", fake_run_realtime_session)
    monkeypatch.setattr(
        "sys.argv",
        ["raa", "--project", "support", "--resume", "DISC-001", "--no-dashboard", "--no-transcript"],
    )
    monkeypatch.setattr(main, "console", SimpleNamespace(print=lambda *_args, **_kwargs: None))

    await main.main()

    assert observed["project_key"] == "support"
    assert observed["requirements"] == ["REQ-SUP"]
