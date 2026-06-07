from __future__ import annotations

from realtime_assistant import prompts


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
