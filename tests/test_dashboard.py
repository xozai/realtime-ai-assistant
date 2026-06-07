from __future__ import annotations

from fastapi.testclient import TestClient

from realtime_assistant.dashboard import app
from realtime_assistant.memory import memory
from realtime_assistant.models import Requirement, UserStory


client = TestClient(app)


def setup_function() -> None:
    memory.clear_requirements()
    memory.set_user_stories([])
    memory.clarified_topics.clear()


def test_root_returns_html() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Discovery Assistant" in response.text


def test_get_requirements_empty() -> None:
    response = client.get("/api/requirements")

    assert response.status_code == 200
    assert response.json() == []


def test_get_requirements_with_data(sample_requirement: Requirement) -> None:
    memory.add_requirement(sample_requirement)

    response = client.get("/api/requirements")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["text"] == sample_requirement.text


def test_get_stories_empty() -> None:
    response = client.get("/api/stories")

    assert response.status_code == 200
    assert response.json() == []


def test_get_stories_with_data(sample_user_story: UserStory) -> None:
    memory.set_user_stories([sample_user_story])

    response = client.get("/api/stories")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["title"] == sample_user_story.title


def test_get_session_returns_summary() -> None:
    response = client.get("/api/session")

    assert response.status_code == 200
    payload = response.json()
    assert "requirement_count" in payload
    assert "story_count" in payload
    assert "session_id" in payload
    assert "started_at" in payload


def test_post_export_with_stories(sample_user_story: UserStory, monkeypatch, tmp_path) -> None:
    memory.set_user_stories([sample_user_story])
    monkeypatch.chdir(tmp_path)

    response = client.post("/api/export")

    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_root_html_contains_auto_refresh() -> None:
    response = client.get("/")

    assert "setInterval" in response.text or "fetch" in response.text
