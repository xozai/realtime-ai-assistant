from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

from realtime_assistant.memory import memory
from realtime_assistant.models import DiscoverySession, Requirement, UserStory
from realtime_assistant.tools import (
    ask_clarifying_question,
    capture_requirement,
    export_user_stories,
    generate_user_stories,
    summarize_requirements,
)


def setup_function() -> None:
    memory.reset_session()
    memory.configure_export_options()
    memory.clear_requirements()
    memory.clear_user_stories()
    memory.clear_clarified_topics()


def test_capture_requirement_returns_success_and_appears_in_memory() -> None:
    result = asyncio.run(capture_requirement("Users can log in with email", "functional"))
    assert result["ok"] is True
    assert result["requirement"]["text"] == "Users can log in with email"
    assert memory.list_requirements()[0].text == "Users can log in with email"


def test_ask_clarifying_question_returns_topic_and_question() -> None:
    result = asyncio.run(
        ask_clarifying_question("authentication", "Do you need SSO support?")
    )
    assert result["topic"] == "authentication"
    assert result["question"] == "Do you need SSO support?"
    assert "authentication" in result["clarified_topics"]


def test_summarize_requirements_returns_requirements_list() -> None:
    memory.create_requirement("Users can log in with email", "functional")
    result = asyncio.run(summarize_requirements())
    assert "requirements" in result
    assert len(result["requirements"]) == 1


def test_generate_user_stories_with_mocked_openai_response(mock_openai_response) -> None:
    memory.add_requirement(
        Requirement(id="REQ-001", text="Users can log in with email", category="functional")
    )
    memory.add_requirement(
        Requirement(id="REQ-002", text="Users can reset passwords", category="functional")
    )
    mock_client = MagicMock()
    mock_client.beta.chat.completions.parse.return_value = mock_openai_response
    with patch("realtime_assistant.llm.OpenAI", return_value=mock_client), patch.dict(
        "os.environ", {"OPENAI_API_KEY": "test-key"}
    ):
        result = asyncio.run(generate_user_stories())
    assert isinstance(result, list)
    assert all(isinstance(story, UserStory) for story in result)
    assert len(memory.list_user_stories()) == 2


def test_export_user_stories_both_creates_json_and_markdown(
    sample_user_story: UserStory,
    tmp_path: Path,
) -> None:
    memory.create_session(DiscoverySession(session_id="DISC-TOOL"))
    memory.configure_export_options(output_dir=tmp_path)
    memory.set_user_stories([sample_user_story])
    result = asyncio.run(export_user_stories("both"))
    assert result["ok"] is True
    assert result["paths"] == [
        str(tmp_path.resolve() / "DISC-TOOL" / "user_stories.json"),
        str(tmp_path.resolve() / "DISC-TOOL" / "user_stories.md"),
    ]
    assert all(Path(path).is_absolute() for path in result["paths"])
    assert Path(result["paths"][0]).exists()
    assert Path(result["paths"][1]).exists()


def test_export_user_stories_accepts_custom_tool_destination(
    sample_user_story: UserStory,
    tmp_path: Path,
) -> None:
    memory.create_session(DiscoverySession(session_id="DISC-CUSTOM"))
    memory.set_user_stories([sample_user_story])

    result = asyncio.run(
        export_user_stories(
            "json",
            output_dir=str(tmp_path / "exports"),
            export_name="custom_stories",
        )
    )

    assert result["paths"] == [
        str(tmp_path.resolve() / "exports" / "DISC-CUSTOM" / "custom_stories.json")
    ]
