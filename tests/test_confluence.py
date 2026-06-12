"""Tests for ConfluenceClient and export_to_confluence tool."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from realtime_assistant.confluence_client import ConfluenceClient, _build_page_body
from realtime_assistant.memory import memory
from realtime_assistant.models import (
    ConfluenceConfig,
    Requirement,
    SessionSummary,
    UserStory,
)
from realtime_assistant.tools import export_to_confluence

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def conf_config() -> ConfluenceConfig:
    return ConfluenceConfig(
        base_url="https://example.atlassian.net",
        user_email="user@example.com",
        api_token="token123",
        space_key="DISC",
    )


@pytest.fixture()
def sample_requirement() -> Requirement:
    return Requirement(id="REQ-001", text="Users can log in with email", category="functional")


@pytest.fixture()
def sample_story() -> UserStory:
    return UserStory(
        id="US-001",
        title="Email login",
        as_a="registered user",
        i_want="to log in with email",
        so_that="I can access the app",
        source_requirement_ids=["REQ-001"],
        acceptance_criteria=["Given a registered user, when they log in, then they see the dashboard."],
        priority="must-have",
        story_points=3,
    )


@pytest.fixture()
def sample_summary() -> SessionSummary:
    return SessionSummary(
        overview="Session covering authentication requirements.",
        key_requirements={"functional": ["Users can log in with email"]},
        open_questions=["Does the team need SSO?"],
        risks_and_assumptions=["Email provider must be available"],
    )


def setup_function() -> None:
    memory.reset_session()
    memory.clear_requirements()
    memory.clear_user_stories()
    memory.clear_clarified_topics()


# ---------------------------------------------------------------------------
# _build_page_body
# ---------------------------------------------------------------------------

def test_build_page_body_includes_requirements(
    sample_requirement: Requirement,
    sample_story: UserStory,
) -> None:
    body = _build_page_body([sample_requirement], [sample_story], None, None, "https://example.atlassian.net")

    assert "REQ-001" in body
    assert "Users can log in with email" in body
    assert "functional" in body


def test_build_page_body_includes_stories(
    sample_requirement: Requirement,
    sample_story: UserStory,
) -> None:
    body = _build_page_body([sample_requirement], [sample_story], None, None, "https://example.atlassian.net")

    assert "US-001" in body
    assert "Email login" in body
    assert "must-have" in body
    assert "registered user" in body
    assert "Given a registered user" in body


def test_build_page_body_includes_executive_summary(
    sample_requirement: Requirement,
    sample_story: UserStory,
    sample_summary: SessionSummary,
) -> None:
    body = _build_page_body(
        [sample_requirement], [sample_story], sample_summary, None, "https://example.atlassian.net"
    )

    assert "Executive Summary" in body
    assert "Session covering authentication requirements." in body
    assert "Does the team need SSO?" in body
    assert "Email provider must be available" in body


def test_build_page_body_includes_jira_links(
    sample_requirement: Requirement,
    sample_story: UserStory,
) -> None:
    body = _build_page_body(
        [sample_requirement], [sample_story], None, ["PROJ-42"], "https://example.atlassian.net"
    )

    assert "PROJ-42" in body
    assert "/browse/PROJ-42" in body


def test_build_page_body_omits_summary_when_none(
    sample_requirement: Requirement,
    sample_story: UserStory,
) -> None:
    body = _build_page_body([sample_requirement], [sample_story], None, None, "https://example.atlassian.net")

    assert "Executive Summary" not in body


def test_build_page_body_escapes_html_special_chars() -> None:
    req = Requirement(id="REQ-X", text="Support <script> & 'quotes'", category="constraint")
    body = _build_page_body([req], [], None, None, "https://example.atlassian.net")

    assert "<script>" not in body
    assert "&lt;script&gt;" in body
    assert "&amp;" in body


# ---------------------------------------------------------------------------
# ConfluenceClient
# ---------------------------------------------------------------------------

def test_confluence_client_create_page(conf_config: ConfluenceConfig) -> None:
    client = ConfluenceClient(conf_config)
    mock_request = MagicMock()

    # find_page returns empty (no existing page), create returns id
    mock_request.side_effect = [
        {"results": []},            # _find_page GET
        {"id": "123456"},           # _create_page POST
    ]

    with patch.object(client, "_request", side_effect=mock_request.side_effect):
        url = client.export_discovery_page("Test Page", [], [])

    assert "123456" in url
    assert "DISC" in url


def test_confluence_client_update_existing_page(conf_config: ConfluenceConfig) -> None:
    client = ConfluenceClient(conf_config)

    mock_request = MagicMock()
    mock_request.side_effect = [
        {"results": [{"id": "999"}]},                    # _find_page GET
        {"id": "999", "version": {"number": 3}},         # _update_page GET version
        {},                                               # _update_page PUT
    ]

    with patch.object(client, "_request", side_effect=mock_request.side_effect):
        url = client.export_discovery_page("Existing Page", [], [])

    assert "999" in url


def test_confluence_client_validate_space_returns_true(conf_config: ConfluenceConfig) -> None:
    client = ConfluenceClient(conf_config)

    with patch.object(client, "_request", return_value={"key": "DISC"}):
        assert client.validate_space("DISC") is True


def test_confluence_client_validate_space_returns_false_on_error(conf_config: ConfluenceConfig) -> None:
    client = ConfluenceClient(conf_config)

    with patch.object(client, "_request", side_effect=RuntimeError("404")):
        assert client.validate_space("BAD") is False


# ---------------------------------------------------------------------------
# export_to_confluence tool
# ---------------------------------------------------------------------------

def test_tool_export_to_confluence_returns_ok_with_page_url(
    sample_requirement: Requirement,
    sample_story: UserStory,
) -> None:
    memory.add_requirement(sample_requirement)
    memory.set_user_stories([sample_story])

    env = {
        "JIRA_BASE_URL": "https://example.atlassian.net",
        "JIRA_USER_EMAIL": "user@example.com",
        "JIRA_API_TOKEN": "token",
        "CONFLUENCE_SPACE_KEY": "DISC",
    }

    with patch("realtime_assistant.confluence_client.ConfluenceClient.validate_space", return_value=True), \
         patch(
             "realtime_assistant.confluence_client.ConfluenceClient.export_discovery_page",
             return_value="https://example.atlassian.net/wiki/spaces/DISC/pages/123",
         ), \
         patch.dict("os.environ", env):
        result = asyncio.run(export_to_confluence())

    assert result["ok"] is True
    assert result["page_url"] == "https://example.atlassian.net/wiki/spaces/DISC/pages/123"
    assert result["requirement_count"] == 1
    assert result["story_count"] == 1


def test_tool_export_to_confluence_returns_error_when_missing_env() -> None:
    with patch.dict("os.environ", {}, clear=True):
        import os
        for key in ("JIRA_BASE_URL", "JIRA_USER_EMAIL", "JIRA_API_TOKEN", "CONFLUENCE_SPACE_KEY"):
            os.environ.pop(key, None)
        result = asyncio.run(export_to_confluence())

    assert result["ok"] is False
    assert "Missing Confluence configuration" in result["error"]


def test_tool_export_to_confluence_returns_error_on_invalid_space(
    sample_requirement: Requirement,
) -> None:
    memory.add_requirement(sample_requirement)
    env = {
        "JIRA_BASE_URL": "https://example.atlassian.net",
        "JIRA_USER_EMAIL": "user@example.com",
        "JIRA_API_TOKEN": "token",
        "CONFLUENCE_SPACE_KEY": "BAD",
    }
    with patch("realtime_assistant.confluence_client.ConfluenceClient.validate_space", return_value=False), \
         patch.dict("os.environ", env):
        result = asyncio.run(export_to_confluence())

    assert result["ok"] is False
    assert "BAD" in result["error"]


def test_tool_export_to_confluence_uses_custom_title(
    sample_requirement: Requirement,
) -> None:
    memory.add_requirement(sample_requirement)
    env = {
        "JIRA_BASE_URL": "https://example.atlassian.net",
        "JIRA_USER_EMAIL": "user@example.com",
        "JIRA_API_TOKEN": "token",
        "CONFLUENCE_SPACE_KEY": "DISC",
    }
    with patch("realtime_assistant.confluence_client.ConfluenceClient.validate_space", return_value=True), \
         patch(
             "realtime_assistant.confluence_client.ConfluenceClient.export_discovery_page",
             return_value="https://example.atlassian.net/wiki/spaces/DISC/pages/999",
         ) as mock_export, \
         patch.dict("os.environ", env):
        result = asyncio.run(export_to_confluence(title="My Custom Page"))

    assert result["ok"] is True
    assert result["page_title"] == "My Custom Page"
    mock_export.assert_called_once()
    call_kwargs = mock_export.call_args
    assert call_kwargs[1]["title"] == "My Custom Page" or call_kwargs[0][0] == "My Custom Page"
