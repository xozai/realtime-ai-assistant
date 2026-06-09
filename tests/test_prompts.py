from __future__ import annotations

from realtime_assistant import prompts
from realtime_assistant.models import Requirement


def test_system_prompt_is_non_empty_string() -> None:
    assert isinstance(prompts.SYSTEM_PROMPT, str)
    assert prompts.SYSTEM_PROMPT.strip()


def test_system_prompt_contains_key_phrases() -> None:
    lower_prompt = prompts.SYSTEM_PROMPT.lower()
    assert "product manager" in lower_prompt
    assert "requirement" in lower_prompt
    assert "user stor" in lower_prompt


def test_story_generation_prompt_constant_is_non_empty_string() -> None:
    assert isinstance(prompts.STORY_GENERATION_PROMPT, str)
    assert prompts.STORY_GENERATION_PROMPT.strip()


def test_voice_mode_intro_constant_is_non_empty_string() -> None:
    assert isinstance(prompts.VOICE_MODE_INTRO, str)
    assert prompts.VOICE_MODE_INTRO.strip()


def test_story_generation_prompt_requires_source_requirement_ids() -> None:
    prompt = prompts.story_generation_prompt(
        [Requirement(id="REQ-001", text="Users can log in", category="functional")]
    )

    assert "REQ-001 [functional]: Users can log in" in prompt
    assert "source_requirement_ids" in prompt
    assert "one or more exact requirement IDs" in prompt


def test_story_generation_prompt_allows_empty_source_ids_without_requirements() -> None:
    prompt = prompts.story_generation_prompt([])

    assert "- No requirements captured." in prompt
    assert "set source_requirement_ids to an empty list" in prompt
