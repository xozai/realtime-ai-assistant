from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

from realtime_assistant.config import AssistantSettings, configure_settings
from realtime_assistant.memory import memory
from realtime_assistant.models import DiscoverySession, Requirement, UserStory
from realtime_assistant.tools import (
    ask_clarifying_question,
    capture_requirement,
    export_user_stories,
    generate_user_stories,
    refine_user_story,
    summarize_requirements,
)


def setup_function() -> None:
    configure_settings(AssistantSettings())
    memory.reset_session()
    memory.configure_export_options()
    memory.clear_requirements()
    memory.clear_user_stories()
    memory.clear_clarified_topics()


def test_capture_requirement_returns_success_and_appears_in_memory() -> None:
    with (
        patch("realtime_assistant.tools.llm.get_embedding", return_value=[1.0, 0.0]),
        patch("realtime_assistant.llm.score_requirement_confidence", return_value="high"),
    ):
        result = asyncio.run(capture_requirement("Users can log in with email", "functional"))
    assert result["ok"] is True
    assert result["requirement"]["text"] == "Users can log in with email"
    assert result["requirement"]["confidence"] == "high"
    assert memory.list_requirements()[0].text == "Users can log in with email"
    assert memory.list_requirements()[0].confidence == "high"


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


def test_summarize_requirements_flags_low_confidence_items() -> None:
    memory.add_requirement(
        Requirement(
            id="REQ-LOW",
            text="Make auth better",
            category="functional",
            confidence="low",
        )
    )

    with patch("realtime_assistant.tools.console") as mock_console:
        result = asyncio.run(summarize_requirements())

    printed_panels = [
        call.args[0]
        for call in mock_console.print.call_args_list
        if getattr(call.args[0], "title", None)
    ]
    assert result["requirements"][0]["confidence"] == "low"
    assert any(
        panel.title == "Low-confidence requirements need clarification"
        for panel in printed_panels
    )


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


def test_generate_user_stories_tool_uses_configured_model() -> None:
    memory.add_requirement(
        Requirement(id="REQ-001", text="Users can log in with email", category="functional")
    )
    configure_settings(AssistantSettings(story_model="gpt-4.1-mini"))

    with patch("realtime_assistant.tools.llm.generate_user_stories", return_value=[]) as mock_generate:
        result = asyncio.run(generate_user_stories())

    assert result == []
    assert mock_generate.call_args.kwargs["model"] == "gpt-4.1-mini"


def test_refine_user_story_tool_uses_configured_model_and_replaces_only_target(
    sample_user_story: UserStory,
) -> None:
    second = sample_user_story.model_copy(update={"id": "US-002", "title": "Password reset"})
    refined = sample_user_story.model_copy(update={"title": "Refined email login"})
    memory.add_requirement(
        Requirement(id="REQ-001", text="Users can log in with email", category="functional")
    )
    memory.set_user_stories([sample_user_story, second])
    configure_settings(AssistantSettings(story_model="gpt-4.1-mini"))

    with patch("realtime_assistant.tools.llm.refine_user_story", return_value=refined) as mock_refine:
        result = asyncio.run(
            refine_user_story(
                sample_user_story.id,
                feedback="Make criteria testable",
                requirement_ids=["REQ-001"],
            )
        )

    assert result["ok"] is True
    assert result["story"]["title"] == "Refined email login"
    assert [story.title for story in memory.list_user_stories()] == [
        "Refined email login",
        "Password reset",
    ]
    assert len(memory.get_current_session().story_refinement_history) == 1
    assert mock_refine.call_args.kwargs["feedback"] == "Make criteria testable"
    assert mock_refine.call_args.kwargs["model"] == "gpt-4.1-mini"


def test_refine_user_story_tool_returns_errors_for_missing_story_and_requirement(
    sample_user_story: UserStory,
) -> None:
    missing_story = asyncio.run(refine_user_story("US-MISSING", feedback="No-op"))
    assert missing_story["ok"] is False
    assert "not found" in missing_story["error"]

    memory.set_user_stories([sample_user_story])
    invalid_requirement = asyncio.run(
        refine_user_story(sample_user_story.id, requirement_ids=["REQ-MISSING"])
    )
    assert invalid_requirement["ok"] is False
    assert invalid_requirement["invalid_requirement_ids"] == ["REQ-MISSING"]


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
