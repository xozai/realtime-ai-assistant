from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

RequirementCategory = Literal["functional", "non-functional", "constraint", "assumption"]
Priority = Literal["must-have", "should-have", "could-have", "wont-have"]


class Requirement(BaseModel):
    id: str = Field(default_factory=lambda: f"REQ-{uuid4().hex[:8].upper()}")
    text: str
    category: RequirementCategory
    captured_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class UserStory(BaseModel):
    id: str
    title: str
    as_a: str = Field(description="The role or persona.")
    i_want: str = Field(description="The capability or goal.")
    so_that: str = Field(description="The business or user benefit.")
    acceptance_criteria: list[str] = Field(default_factory=list)
    priority: Priority
    story_points: int

    @field_validator("story_points")
    @classmethod
    def validate_story_points(cls, value: int) -> int:
        allowed = {1, 2, 3, 5, 8, 13}
        if value not in allowed:
            raise ValueError(f"story_points must be one of {sorted(allowed)}")
        return value


class UserStorySet(BaseModel):
    user_stories: list[UserStory]


class JiraConfig(BaseModel):
    base_url: str
    user_email: str
    api_token: str
    story_points_field: str = "story_points"

    @classmethod
    def from_env(cls) -> JiraConfig:
        return cls(
            base_url=os.environ["JIRA_BASE_URL"],
            user_email=os.environ["JIRA_USER_EMAIL"],
            api_token=os.environ["JIRA_API_TOKEN"],
            story_points_field=os.environ.get("JIRA_STORY_POINTS_FIELD", "story_points"),
        )


class DiscoverySession(BaseModel):
    session_id: str = Field(default_factory=lambda: f"DISC-{uuid4().hex[:8].upper()}")
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    requirements: list[Requirement] = Field(default_factory=list)
    user_stories: list[UserStory] = Field(default_factory=list)
