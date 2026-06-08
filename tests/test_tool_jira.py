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

    with patch.dict("os.environ", jira_env(), clear=True), patch(
        "realtime_assistant.tools.JiraClient", return_value=mock_client
    ):
        result = asyncio.run(submit_stories_to_jira("PROJ"))

    assert result["ok"] is True
    assert result["project_key"] == "PROJ"
    assert result["created_issues"] == ["PROJ-1", "PROJ-2"]
    assert result["count"] == 2


def test_submit_stories_partial_failure() -> None:
    memory.set_user_stories([make_story("US-001", "First story"), make_story("US-002", "Second story")])
    mock_client = MagicMock()
    mock_client.validate_project.return_value = True
    mock_client.create_issue.side_effect = ["PROJ-1", RuntimeError("Jira rejected story")]

    with patch.dict("os.environ", jira_env(), clear=True), patch(
        "realtime_assistant.tools.JiraClient", return_value=mock_client
    ):
        result = asyncio.run(submit_stories_to_jira("PROJ"))

    assert result["ok"] is False
    assert "Failed to submit stories to Jira" in result["error"]
    assert "Jira rejected story" in result["error"]
