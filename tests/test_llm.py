from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from realtime_assistant import llm
from realtime_assistant.llm import (
    score_requirement_confidence,
    validate_story_source_requirement_ids,
)
from realtime_assistant.memory import memory
from realtime_assistant.models import DiscoverySession, Requirement, UserStory, UserStorySet


def make_story(source_requirement_ids: list[str]) -> UserStory:
    return UserStory(
        id="US-001",
        title="Email login",
        as_a="registered user",
        i_want="to log in with email",
        so_that="I can access my account",
        source_requirement_ids=source_requirement_ids,
        acceptance_criteria=["Given valid credentials, then access is granted."],
        priority="must-have",
        story_points=3,
    )


def make_requirements() -> list[Requirement]:
    return [
        Requirement(id="REQ-001", text="Users can log in", category="functional"),
        Requirement(id="REQ-002", text="Users can reset passwords", category="functional"),
    ]


def test_validate_story_source_requirement_ids_keeps_valid_current_ids() -> None:
    stories = validate_story_source_requirement_ids(
        [make_story(["REQ-001", "REQ-404", "REQ-001"])],
        make_requirements(),
    )

    assert stories[0].source_requirement_ids == ["REQ-001"]


def test_validate_story_source_requirement_ids_falls_back_when_missing_or_invalid() -> None:
    stories = validate_story_source_requirement_ids(
        [make_story(["REQ-404"])],
        make_requirements(),
    )

    assert stories[0].source_requirement_ids == ["REQ-001", "REQ-002"]


def test_validate_story_source_requirement_ids_clears_ids_without_requirements() -> None:
    stories = validate_story_source_requirement_ids([make_story(["REQ-001"])], [])

    assert stories[0].source_requirement_ids == []


def test_score_requirement_confidence_calls_openai_and_returns_score() -> None:
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="low"))]
    )
    session = DiscoverySession(requirements=make_requirements())

    with patch("realtime_assistant.llm.OpenAI", return_value=mock_client), patch.dict(
        "os.environ", {"OPENAI_API_KEY": "test-key"}
    ):
        score = score_requirement_confidence("Make login better", "functional", session)

    assert score == "low"
    mock_client.chat.completions.create.assert_called_once()


def test_score_requirement_confidence_defaults_to_medium_for_unexpected_output() -> None:
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="unclear"))]
    )

    with patch("realtime_assistant.llm.OpenAI", return_value=mock_client), patch.dict(
        "os.environ", {"OPENAI_API_KEY": "test-key"}
    ):
        score = score_requirement_confidence("Users can log in", "functional", DiscoverySession())

    assert score == "medium"


def test_generate_user_stories_accumulates_chat_usage() -> None:
    memory.reset_session()
    parsed = UserStorySet(user_stories=[make_story(["REQ-001"])])
    completion = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed))],
        usage=SimpleNamespace(prompt_tokens=1000, completion_tokens=250),
    )
    mock_client = MagicMock()
    mock_client.beta.chat.completions.parse.return_value = completion

    with patch("realtime_assistant.llm.OpenAI", return_value=mock_client), patch.dict(
        "os.environ", {"OPENAI_API_KEY": "test-key"}
    ):
        stories = llm.generate_user_stories(make_requirements())

    assert len(stories) == 1
    usage = memory.get_current_session().costs.chat_completions
    assert usage.input_tokens == 1000
    assert usage.output_tokens == 250


def test_generate_user_stories_uses_default_model() -> None:
    parsed = UserStorySet(user_stories=[make_story(["REQ-001"])])
    completion = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed))],
    )
    mock_client = MagicMock()
    mock_client.beta.chat.completions.parse.return_value = completion

    with patch("realtime_assistant.llm.OpenAI", return_value=mock_client), patch.dict(
        "os.environ", {"OPENAI_API_KEY": "test-key"}
    ):
        llm.generate_user_stories(make_requirements())

    assert mock_client.beta.chat.completions.parse.call_args.kwargs["model"] == "gpt-4o"


def test_generate_user_stories_uses_selected_model() -> None:
    parsed = UserStorySet(user_stories=[make_story(["REQ-001"])])
    completion = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed))],
    )
    mock_client = MagicMock()
    mock_client.beta.chat.completions.parse.return_value = completion

    with patch("realtime_assistant.llm.OpenAI", return_value=mock_client), patch.dict(
        "os.environ", {"OPENAI_API_KEY": "test-key"}
    ):
        llm.generate_user_stories(make_requirements(), model="gpt-4.1")

    assert mock_client.beta.chat.completions.parse.call_args.kwargs["model"] == "gpt-4.1"
