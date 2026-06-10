from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from realtime_assistant.memory import memory
from realtime_assistant.models import UserStory
from realtime_assistant.tools import submit_stories_to_jira


def setup_function() -> None:
    memory.clear_requirements()
    memory.clear_user_stories()
    memory.clear_clarified_topics()


def make_story(story_id: str, title: str) -> UserStory:
    return UserStory(
        id=story_id,
        title=title,
        as_a="registered user",
        i_want="to use the feature",
        so_that="I get value",
        source_requirement_ids=["REQ-001"],
        acceptance_criteria=["Given the feature is available, then I can use it."],
        priority="must-have",
        story_points=3,
    )


def jira_env() -> dict[str, str]:
    return {
        "JIRA_BASE_URL": "https://example.atlassian.net",
        "JIRA_USER_EMAIL": "user@example.com",
        "JIRA_API_TOKEN": "token",
    }


def test_submit_stories_no_stories_returns_error() -> None:
    mock_client = MagicMock()
    mock_client.validate_project.return_value = True
    with patch.dict("os.environ", jira_env(), clear=True), patch(
        "realtime_assistant.tools.JiraClient", return_value=mock_client
    ):
        result = asyncio.run(submit_stories_to_jira("PROJ"))

    assert result["ok"] is False
    assert result["error"] == "No user stories in memory. Run generate_user_stories first."


def test_submit_stories_without_jira_project_key_warns() -> None:
    result = asyncio.run(submit_stories_to_jira())

    assert result["ok"] is False
    assert result["error"] == "Jira project_key is required."
    assert "separate from the discovery project key" in result["warning"]
    assert result["discovery_project_key"] == memory.get_current_session().project_key


def test_submit_stories_missing_env_returns_error() -> None:
    with patch.dict("os.environ", {}, clear=True):
        result = asyncio.run(submit_stories_to_jira("PROJ"))

    assert result["ok"] is False
    assert "Missing Jira configuration environment variable" in result["error"]


def test_submit_stories_invalid_project_returns_error() -> None:
    mock_client = MagicMock()
    mock_client.validate_project.return_value = False
    with patch.dict("os.environ", jira_env(), clear=True), patch(
        "realtime_assistant.tools.JiraClient", return_value=mock_client
    ):
        result = asyncio.run(submit_stories_to_jira("PROJ"))

    assert result["ok"] is False
    assert "not found or is not accessible" in result["error"]


def test_submit_stories_success() -> None:
    memory.set_user_stories([make_story("US-001", "First story"), make_story("US-002", "Second story")])
    mock_client = MagicMock()
    mock_client.validate_project.return_value = True
    mock_client.create_issue.side_effect = ["PROJ-1", "PROJ-2"]
    mock_client.issue_url.side_effect = lambda key: f"https://example.atlassian.net/browse/{key}"

    with patch.dict("os.environ", jira_env(), clear=True), patch(
        "realtime_assistant.tools.JiraClient", return_value=mock_client
    ):
        result = asyncio.run(submit_stories_to_jira("PROJ"))

    assert result["ok"] is True
    assert result["project_key"] == "PROJ"
    assert result["created_issues"] == ["PROJ-1", "PROJ-2"]
    assert result["count"] == 2
    assert result["success_count"] == 2
    assert result["failure_count"] == 0
    assert [item["status"] for item in result["results"]] == ["success", "success"]
    assert result["results"][0]["issue_key"] == "PROJ-1"
    assert result["results"][0]["issue_url"] == "https://example.atlassian.net/browse/PROJ-1"


def test_submit_stories_dry_run_returns_preview_without_network() -> None:
    memory.set_user_stories([make_story("US-001", "First story")])

    with patch.dict("os.environ", {"JIRA_STORY_POINTS_FIELD": "customfield_10016"}, clear=True), patch(
        "realtime_assistant.jira_client.request.urlopen"
    ) as urlopen:
        result = asyncio.run(submit_stories_to_jira("PROJ", dry_run=True))

    urlopen.assert_not_called()
    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["created_issues"] == []
    assert result["count"] == 0
    assert result["skipped_count"] == 1
    assert result["results"][0]["status"] == "skipped"
    assert result["results"][0]["skipped_reason"] == "dry_run"
    assert result["results"][0]["story_points_field"] == "customfield_10016"
    assert result["results"][0]["payload"]["fields"]["summary"] == "First story"


def test_submit_stories_partial_failure_continues_after_failed_story() -> None:
    memory.set_user_stories(
        [
            make_story("US-001", "First story"),
            make_story("US-002", "Second story"),
            make_story("US-003", "Third story"),
        ]
    )
    mock_client = MagicMock()
    mock_client.validate_project.return_value = True
    mock_client.create_issue.side_effect = [
        "PROJ-1",
        RuntimeError("Jira rejected story"),
        "PROJ-3",
    ]
    mock_client.issue_url.side_effect = lambda key: f"https://example.atlassian.net/browse/{key}"

    with patch.dict("os.environ", jira_env(), clear=True), patch(
        "realtime_assistant.tools.JiraClient", return_value=mock_client
    ):
        result = asyncio.run(submit_stories_to_jira("PROJ"))

    assert result["ok"] is False
    assert result["created_issues"] == ["PROJ-1", "PROJ-3"]
    assert result["count"] == 2
    assert result["success_count"] == 2
    assert result["failure_count"] == 1
    assert [item["status"] for item in result["results"]] == ["success", "failure", "success"]
    assert result["results"][1]["story_id"] == "US-002"
    assert result["results"][1]["error"] == "Jira rejected story"
    assert mock_client.create_issue.call_count == 3
