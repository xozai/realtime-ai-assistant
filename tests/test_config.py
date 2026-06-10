from __future__ import annotations

from unittest.mock import patch

from realtime_assistant.config import DEFAULT_STORY_GENERATION_MODEL, load_settings
from realtime_assistant.main import parse_args


def test_story_model_cli_flag_wins_over_env(monkeypatch) -> None:
    monkeypatch.setenv("STORY_GENERATION_MODEL", "gpt-env-story")

    with patch("sys.argv", ["raa", "--story-model", "gpt-cli-story"]):
        args = parse_args()

    settings = load_settings(story_model=args.story_model)
    assert settings.story_model == "gpt-cli-story"


def test_story_model_env_wins_over_default(monkeypatch) -> None:
    monkeypatch.setenv("STORY_GENERATION_MODEL", "gpt-env-story")

    with patch("sys.argv", ["raa"]):
        args = parse_args()

    settings = load_settings(story_model=args.story_model)
    assert settings.story_model == "gpt-env-story"


def test_story_model_uses_existing_default_without_cli_or_env(monkeypatch) -> None:
    monkeypatch.delenv("STORY_GENERATION_MODEL", raising=False)

    with patch("sys.argv", ["raa"]):
        args = parse_args()

    settings = load_settings(story_model=args.story_model)
    assert settings.story_model == DEFAULT_STORY_GENERATION_MODEL
