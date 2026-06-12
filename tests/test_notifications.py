from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib import error

from realtime_assistant.memory import memory
from realtime_assistant.models import DiscoverySession, Requirement, UserStory
from realtime_assistant.notifications import SlackNotifier, TeamsNotifier, notify_story_ready
from realtime_assistant.tools import export_user_stories, submit_stories_to_jira


def setup_function() -> None:
    memory.reset_session()
    memory.configure_export_options()
    memory.clear_requirements()
    memory.clear_user_stories()
    memory.clear_clarified_topics()


def make_response(status: int = 200, body: str = "ok") -> MagicMock:
    response = MagicMock()
    response.getcode.return_value = status
    response.read.return_value = body.encode("utf-8")
    response.__enter__.return_value = response
    response.__exit__.return_value = None
    return response


def payload_from_request(req) -> dict:
    return json.loads(req.data.decode("utf-8"))


def make_story(story_id: str = "US-001", title: str = "Email login") -> UserStory:
    return UserStory(
        id=story_id,
        title=title,
        as_a="registered user",
        i_want="to log in with email",
        so_that="I can access my account",
        source_requirement_ids=["REQ-001"],
        acceptance_criteria=["Given valid credentials, then access is granted."],
        priority="must-have",
        story_points=3,
    )


def test_slack_notifier_posts_expected_payload() -> None:
    notifier = SlackNotifier("https://hooks.slack.test/services/T000/B000/XXX")

    with patch(
        "realtime_assistant.notifications.request.urlopen",
        return_value=make_response(),
    ) as urlopen:
        result = notifier.notify(
            story_count=2,
            requirement_count=3,
            export_paths=["/tmp/user_stories.json", "/tmp/user_stories.md"],
            jira_keys=["PROJ-1", "PROJ-2"],
        )

    payload = payload_from_request(urlopen.call_args.args[0])
    assert result.sent is True
    assert payload == {
        "text": (
            "User stories ready.\n"
            "Stories: 2\n"
            "Requirements: 3\n"
            "Exports: /tmp/user_stories.json, /tmp/user_stories.md\n"
            "Jira keys: PROJ-1, PROJ-2"
        )
    }


def test_teams_notifier_posts_expected_payload() -> None:
    notifier = TeamsNotifier("https://teams.example/webhook")

    with patch(
        "realtime_assistant.notifications.request.urlopen",
        return_value=make_response(),
    ) as urlopen:
        result = notifier.notify(
            story_count=1,
            requirement_count=1,
            export_paths=[],
            jira_keys=[],
        )

    payload = payload_from_request(urlopen.call_args.args[0])
    assert result.sent is True
    assert payload["text"] == (
        "User stories ready.\n"
        "Stories: 1\n"
        "Requirements: 1\n"
        "Exports: None\n"
        "Jira keys: None"
    )


def test_notify_story_ready_disabled_when_env_missing() -> None:
    with patch.dict("os.environ", {}, clear=True), patch(
        "realtime_assistant.notifications.request.urlopen"
    ) as urlopen:
        results = notify_story_ready(story_count=1, requirement_count=2)

    urlopen.assert_not_called()
    assert [(result.notifier, result.enabled, result.sent) for result in results] == [
        ("slack", False, False),
        ("teams", False, False),
    ]


def test_export_user_stories_sends_notification(
    sample_user_story: UserStory,
    tmp_path: Path,
) -> None:
    memory.create_session(DiscoverySession(session_id="DISC-NOTIFY"))
    memory.configure_export_options(output_dir=tmp_path)
    memory.add_requirement(Requirement(id="REQ-001", text="Users log in", category="functional"))
    memory.set_user_stories([sample_user_story])

    with patch.dict(
        "os.environ",
        {"SLACK_WEBHOOK_URL": "https://hooks.slack.test/services/T000/B000/XXX"},
        clear=True,
    ), patch(
        "realtime_assistant.notifications.request.urlopen",
        return_value=make_response(),
    ) as urlopen:
        result = asyncio.run(export_user_stories("both"))

    payload = payload_from_request(urlopen.call_args.args[0])
    assert result["ok"] is True
    assert result["notifications"][0] == {"notifier": "slack", "enabled": True, "sent": True}
    assert "Stories: 1" in payload["text"]
    assert "Requirements: 1" in payload["text"]
    assert result["paths"][0] in payload["text"]
    assert result["paths"][1] in payload["text"]


def test_submit_stories_to_jira_sends_notification_with_keys() -> None:
    memory.add_requirement(Requirement(id="REQ-001", text="Users log in", category="functional"))
    memory.set_user_stories([make_story("US-001", "First"), make_story("US-002", "Second")])
    mock_client = MagicMock()
    mock_client.validate_project.return_value = True
    mock_client.create_issue.side_effect = ["PROJ-1", "PROJ-2"]
    mock_client.issue_url.side_effect = lambda key: f"https://example.atlassian.net/browse/{key}"

    with patch.dict(
        "os.environ",
        {
            "JIRA_BASE_URL": "https://example.atlassian.net",
            "JIRA_USER_EMAIL": "user@example.com",
            "JIRA_API_TOKEN": "token",
            "SLACK_WEBHOOK_URL": "https://hooks.slack.test/services/T000/B000/XXX",
        },
        clear=True,
    ), patch("realtime_assistant.tools.JiraClient", return_value=mock_client), patch(
        "realtime_assistant.notifications.request.urlopen",
        return_value=make_response(),
    ) as urlopen:
        result = asyncio.run(submit_stories_to_jira("PROJ"))

    payload = payload_from_request(urlopen.call_args.args[0])
    assert result["ok"] is True
    assert result["created_issues"] == ["PROJ-1", "PROJ-2"]
    assert "Stories: 2" in payload["text"]
    assert "Requirements: 1" in payload["text"]
    assert "Jira keys: PROJ-1, PROJ-2" in payload["text"]


def test_notification_failure_logs_warning_and_does_not_break_export(
    sample_user_story: UserStory,
    tmp_path: Path,
    caplog,
) -> None:
    memory.create_session(DiscoverySession(session_id="DISC-NOTIFY-FAIL"))
    memory.configure_export_options(output_dir=tmp_path)
    memory.add_requirement(Requirement(id="REQ-001", text="Users log in", category="functional"))
    memory.set_user_stories([sample_user_story])

    with caplog.at_level(logging.WARNING, logger="realtime_assistant"), patch.dict(
        "os.environ",
        {"SLACK_WEBHOOK_URL": "https://hooks.slack.test/services/T000/B000/XXX"},
        clear=True,
    ), patch(
        "realtime_assistant.notifications.request.urlopen",
        side_effect=error.URLError("network down"),
    ):
        result = asyncio.run(export_user_stories("json"))

    assert result["ok"] is True
    assert result["notifications"][0]["sent"] is False
    assert "network down" in result["notifications"][0]["error"]
    assert "Failed to send slack notification" in caplog.text
