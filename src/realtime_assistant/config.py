from __future__ import annotations

import os

from pydantic import BaseModel, Field

DEFAULT_STORY_GENERATION_MODEL = "gpt-4o"
STORY_GENERATION_MODEL_ENV = "STORY_GENERATION_MODEL"


class AssistantSettings(BaseModel):
    story_model: str = Field(default=DEFAULT_STORY_GENERATION_MODEL)


_settings: AssistantSettings | None = None


def load_settings(*, story_model: str | None = None) -> AssistantSettings:
    resolved_story_model = (
        story_model
        or os.getenv(STORY_GENERATION_MODEL_ENV)
        or DEFAULT_STORY_GENERATION_MODEL
    )
    return AssistantSettings(story_model=resolved_story_model)


def configure_settings(settings: AssistantSettings) -> None:
    global _settings
    _settings = settings


def get_settings() -> AssistantSettings:
    return _settings or load_settings()
