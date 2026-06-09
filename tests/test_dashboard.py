from __future__ import annotations

from fastapi.testclient import TestClient

from realtime_assistant.dashboard import app
from realtime_assistant.memory import memory
from realtime_assistant.models import DiscoverySession, Requirement, UserStory

client = TestClient(app)


def setup_function() -> None:
    memory.reset_session()
    memory.configure_export_options()
    memory.clear_requirements()
    memory.clear_user_stories()
    memory.clear_clarified_topics()


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
    assert payload[0]["source_requirement_ids"] == ["REQ-001"]


def test_patch_requirement_updates_text_and_category(sample_requirement: Requirement) -> None:
    memory.add_requirement(sample_requirement)

    response = client.patch(
        f"/api/requirements/{sample_requirement.id}",
        json={"text": "Users can sign in with SSO", "category": "constraint"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == sample_requirement.id
    assert payload["text"] == "Users can sign in with SSO"
    assert payload["category"] == "constraint"
    assert memory.get_requirement(sample_requirement.id).text == "Users can sign in with SSO"


def test_delete_requirement_removes_item_and_refreshes_count(sample_requirement: Requirement) -> None:
    memory.add_requirement(sample_requirement)

    response = client.delete(f"/api/requirements/{sample_requirement.id}")

    assert response.status_code == 200
    assert response.json()["requirement_count"] == 0
    assert client.get("/api/requirements").json() == []


def test_patch_story_updates_fields_and_acceptance_criteria(sample_user_story: UserStory) -> None:
    memory.set_user_stories([sample_user_story])

    response = client.patch(
        f"/api/stories/{sample_user_story.id}",
        json={
            "title": "SSO login",
            "as_a": "enterprise user",
            "i_want": "to sign in with my identity provider",
            "so_that": "I can use company credentials",
            "acceptance_criteria": [
                "Given SSO is enabled, when I select my provider, then auth starts.",
                "Given auth succeeds, when I return, then I am signed in.",
            ],
            "priority": "should-have",
            "story_points": 5,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "SSO login"
    assert payload["as_a"] == "enterprise user"
    assert payload["acceptance_criteria"] == [
        "Given SSO is enabled, when I select my provider, then auth starts.",
        "Given auth succeeds, when I return, then I am signed in.",
    ]
    assert payload["priority"] == "should-have"
    assert payload["story_points"] == 5
    assert payload["source_requirement_ids"] == ["REQ-001"]


def test_patch_missing_requirement_returns_404() -> None:
    response = client.patch("/api/requirements/REQ-MISSING", json={"text": "No-op"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Requirement REQ-MISSING not found."


def test_delete_missing_requirement_returns_404() -> None:
    response = client.delete("/api/requirements/REQ-MISSING")

    assert response.status_code == 404
    assert response.json()["detail"] == "Requirement REQ-MISSING not found."


def test_patch_missing_story_returns_404() -> None:
    response = client.patch("/api/stories/US-MISSING", json={"title": "No-op"})

    assert response.status_code == 404
    assert response.json()["detail"] == "User story US-MISSING not found."


def test_invalid_requirement_category_returns_clear_error(sample_requirement: Requirement) -> None:
    memory.add_requirement(sample_requirement)

    response = client.patch(
        f"/api/requirements/{sample_requirement.id}",
        json={"category": "invalid"},
    )

    assert response.status_code == 422
    assert "category" in response.text
    assert "functional" in response.text


def test_invalid_story_priority_returns_clear_error(sample_user_story: UserStory) -> None:
    memory.set_user_stories([sample_user_story])

    response = client.patch(
        f"/api/stories/{sample_user_story.id}",
        json={"priority": "urgent"},
    )

    assert response.status_code == 422
    assert "priority" in response.text
    assert "must-have" in response.text


def test_invalid_story_points_returns_clear_error(sample_user_story: UserStory) -> None:
    memory.set_user_stories([sample_user_story])

    response = client.patch(
        f"/api/stories/{sample_user_story.id}",
        json={"story_points": 4},
    )

    assert response.status_code == 422
    assert "story_points must be one of" in response.json()["detail"]


def test_get_session_returns_summary() -> None:
    response = client.get("/api/session")

    assert response.status_code == 200
    payload = response.json()
    assert "requirement_count" in payload
    assert "story_count" in payload
    assert "session_id" in payload
    assert "started_at" in payload


def test_post_export_with_stories(sample_user_story: UserStory, monkeypatch, tmp_path) -> None:
    memory.create_session(DiscoverySession(session_id="DISC-DASH"))
    memory.configure_export_options(output_dir=tmp_path)
    memory.set_user_stories([sample_user_story])
    monkeypatch.chdir(tmp_path)

    response = client.post("/api/export")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["paths"] == [
        str(tmp_path.resolve() / "DISC-DASH" / "user_stories.json"),
        str(tmp_path.resolve() / "DISC-DASH" / "user_stories.md"),
    ]


def test_root_html_contains_auto_refresh() -> None:
    response = client.get("/")

    assert "setInterval" in response.text or "fetch" in response.text


def test_root_html_renders_story_source_requirements() -> None:
    response = client.get("/")

    assert "source_requirement_ids" in response.text
    assert "Source" in response.text


def test_root_html_contains_edit_controls_and_api_hooks() -> None:
    response = client.get("/")

    assert 'data-action="edit-requirement"' in response.text
    assert 'data-action="delete-requirement"' in response.text
    assert 'data-action="edit-story"' in response.text
    assert 'method: "PATCH"' in response.text
    assert 'method: "DELETE"' in response.text


# ---------------------------------------------------------------------------
# Summary endpoints
# ---------------------------------------------------------------------------

def test_get_summary_returns_null_when_not_set() -> None:
    response = client.get("/api/summary")

    assert response.status_code == 200
    assert response.json() == {"summary": None}


def test_get_summary_returns_summary_when_set() -> None:
    from realtime_assistant.models import SessionSummary
    summary = SessionSummary(
        overview="Test overview",
        key_requirements={"functional": ["Login"]},
        open_questions=["SSO needed?"],
        risks_and_assumptions=["Email available"],
    )
    session = memory.get_current_session()
    memory.session = session.model_copy(update={"summary": summary})

    response = client.get("/api/summary")

    assert response.status_code == 200
    payload = response.json()["summary"]
    assert payload["overview"] == "Test overview"
    assert payload["key_requirements"] == {"functional": ["Login"]}
    assert payload["open_questions"] == ["SSO needed?"]


def test_post_generate_summary_calls_llm_and_returns_summary() -> None:
    from unittest.mock import patch

    from realtime_assistant.models import SessionSummary
    expected = SessionSummary(
        overview="Discovery overview",
        key_requirements={"functional": ["Users log in"]},
        open_questions=[],
        risks_and_assumptions=[],
    )
    with patch("realtime_assistant.llm.generate_session_summary", return_value=expected), \
         patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
        response = client.post("/api/summary/generate")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["summary"]["overview"] == "Discovery overview"


def test_root_html_contains_generate_summary_button() -> None:
    response = client.get("/")

    assert "Generate Summary" in response.text
    assert "summary-button" in response.text
    assert "/api/summary/generate" in response.text
