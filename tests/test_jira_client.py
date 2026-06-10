from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
from urllib import error

import pytest

from realtime_assistant.jira_client import JiraClient
from realtime_assistant.models import JiraConfig, UserStory


def make_config() -> JiraConfig:
    return JiraConfig(
        base_url="https://example.atlassian.net",
        user_email="user@example.com",
        api_token="token",
    )


def make_story(priority: str = "must-have") -> UserStory:
    return UserStory(
        id="US-001",
        title="Email login",
        as_a="registered user",
        i_want="to log in with my email address",
        so_that="I can securely access my account",
        source_requirement_ids=["REQ-001", "REQ-002"],
        acceptance_criteria=[
            "Given valid credentials, then access is granted.",
            "Given invalid credentials, then an error is shown.",
        ],
        priority=priority,
        story_points=3,
    )


def make_response(status: int = 200, body: dict | None = None) -> MagicMock:
    response = MagicMock()
    response.getcode.return_value = status
    response.read.return_value = json.dumps(body or {}).encode("utf-8")
    response.__enter__.return_value = response
    response.__exit__.return_value = None
    return response


def payload_from_request(req) -> dict:
    return json.loads(req.data.decode("utf-8"))


def test_create_issue_returns_issue_key() -> None:
    client = JiraClient(make_config())
    with patch("realtime_assistant.jira_client.request.urlopen", return_value=make_response(201, {"key": "PROJ-1"})):
        assert client.create_issue("PROJ", make_story()) == "PROJ-1"


def test_create_issue_formats_description_correctly() -> None:
    client = JiraClient(make_config())
    with patch("realtime_assistant.jira_client.request.urlopen", return_value=make_response(201, {"key": "PROJ-1"})) as urlopen:
        client.create_issue("PROJ", make_story())

    payload = payload_from_request(urlopen.call_args.args[0])
    description = payload["fields"]["description"]["content"][0]["content"][0]["text"]
    assert "As a" in description
    assert "I want" in description
    assert "so that" in description
    assert "Traceability:" in description
    assert "Source Requirements: REQ-001, REQ-002" in description
    assert "Given valid credentials, then access is granted." in description
    assert "Given invalid credentials, then an error is shown." in description


def test_preview_issue_returns_exact_submission_payload_without_network() -> None:
    client = JiraClient(make_config())
    with patch("realtime_assistant.jira_client.request.urlopen") as urlopen:
        preview = client.preview_issue("PROJ", make_story())

    urlopen.assert_not_called()
    assert preview["story_id"] == "US-001"
    assert preview["summary"] == "Email login"
    assert preview["description"] == JiraClient._format_description(make_story())
    assert preview["priority"] == "Highest"
    assert preview["story_points_field"] == "story_points"
    assert preview["payload"] == client.issue_payload("PROJ", make_story())
    assert preview["payload"]["fields"]["description"]["content"][0]["content"][0]["text"] == preview["description"]


def test_create_issue_maps_priority_must_have_to_highest() -> None:
    client = JiraClient(make_config())
    with patch("realtime_assistant.jira_client.request.urlopen", return_value=make_response(201, {"key": "PROJ-1"})) as urlopen:
        client.create_issue("PROJ", make_story("must-have"))

    payload = payload_from_request(urlopen.call_args.args[0])
    assert payload["fields"]["priority"]["name"] == "Highest"


def test_create_issue_maps_priority_wont_have_to_low() -> None:
    client = JiraClient(make_config())
    with patch("realtime_assistant.jira_client.request.urlopen", return_value=make_response(201, {"key": "PROJ-1"})) as urlopen:
        client.create_issue("PROJ", make_story("wont-have"))

    payload = payload_from_request(urlopen.call_args.args[0])
    assert payload["fields"]["priority"]["name"] == "Low"


def test_validate_project_returns_true_on_200() -> None:
    client = JiraClient(make_config())
    with patch("realtime_assistant.jira_client.request.urlopen", return_value=make_response(200, {"key": "PROJ"})):
        assert client.validate_project("PROJ") is True


def test_validate_project_returns_false_on_404() -> None:
    client = JiraClient(make_config())
    http_error = error.HTTPError(
        url="https://example.atlassian.net/rest/api/3/project/PROJ",
        code=404,
        msg="Not Found",
        hdrs={},
        fp=MagicMock(read=MagicMock(return_value=b"not found")),
    )
    with patch("realtime_assistant.jira_client.request.urlopen", side_effect=http_error):
        assert client.validate_project("PROJ") is False


def test_create_issue_raises_on_non_2xx() -> None:
    client = JiraClient(make_config())
    with patch("realtime_assistant.jira_client.request.urlopen", return_value=make_response(400, {"error": "bad request"})):
        with pytest.raises(RuntimeError):
            client.create_issue("PROJ", make_story())
