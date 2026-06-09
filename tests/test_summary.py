from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from realtime_assistant import llm
from realtime_assistant.memory import memory
from realtime_assistant.models import Requirement, SessionSummary
from realtime_assistant.tools import generate_session_summary

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_summary(**kwargs) -> SessionSummary:
    defaults = dict(
        overview="This session covered authentication requirements.",
        key_requirements={
            "functional": ["Users can log in with email"],
            "constraint": ["Must support OAuth2"],
        },
        open_questions=["Does the team need SSO?"],
        risks_and_assumptions=["Assumes email provider is available."],
    )
    defaults.update(kwargs)
    return SessionSummary(**defaults)


def setup_function() -> None:
    memory.reset_session()
    memory.clear_requirements()
    memory.clear_user_stories()
    memory.clear_clarified_topics()


# ---------------------------------------------------------------------------
# llm.generate_session_summary — unit tests (mocked OpenAI)
# ---------------------------------------------------------------------------

def test_generate_session_summary_returns_session_summary_model() -> None:
    req = Requirement(id="REQ-001", text="Users can log in with email", category="functional")
    expected = _make_summary()

    mock_client = MagicMock()
    mock_parsed = MagicMock()
    mock_parsed.choices = [MagicMock(message=MagicMock(parsed=expected))]
    mock_client.beta.chat.completions.parse.return_value = mock_parsed

    with patch("realtime_assistant.llm.OpenAI", return_value=mock_client), \
         patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
        result = llm.generate_session_summary([req], ["authentication"])

    assert isinstance(result, SessionSummary)
    assert result.overview == expected.overview
    assert result.open_questions == expected.open_questions


def test_generate_session_summary_raises_without_api_key() -> None:
    with patch.dict("os.environ", {}, clear=True):
        import os
        os.environ.pop("OPENAI_API_KEY", None)
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
            llm.generate_session_summary([], [])


def test_generate_session_summary_empty_requirements() -> None:
    """Summary generation with empty requirements should still call OpenAI."""
    expected = _make_summary(
        overview="No requirements were captured.",
        key_requirements={},
        open_questions=[],
        risks_and_assumptions=[],
    )
    mock_client = MagicMock()
    mock_parsed = MagicMock()
    mock_parsed.choices = [MagicMock(message=MagicMock(parsed=expected))]
    mock_client.beta.chat.completions.parse.return_value = mock_parsed

    with patch("realtime_assistant.llm.OpenAI", return_value=mock_client), \
         patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
        result = llm.generate_session_summary([], [])

    assert isinstance(result, SessionSummary)
    assert result.overview == "No requirements were captured."


# ---------------------------------------------------------------------------
# tools.generate_session_summary — integration with memory
# ---------------------------------------------------------------------------

def test_tool_generate_session_summary_stores_on_session() -> None:
    memory.create_requirement("Users can log in", "functional")
    memory.mark_clarified("authentication")

    expected = _make_summary()

    with patch("realtime_assistant.llm.generate_session_summary", return_value=expected), \
         patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
        result = asyncio.run(generate_session_summary())

    assert result["ok"] is True
    assert result["summary"]["overview"] == expected.overview
    assert memory.get_current_session().summary is not None
    assert memory.get_current_session().summary.overview == expected.overview


def test_tool_generate_session_summary_returns_structured_fields() -> None:
    expected = _make_summary()

    with patch("realtime_assistant.llm.generate_session_summary", return_value=expected), \
         patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
        result = asyncio.run(generate_session_summary())

    s = result["summary"]
    assert "key_requirements" in s
    assert "open_questions" in s
    assert "risks_and_assumptions" in s
