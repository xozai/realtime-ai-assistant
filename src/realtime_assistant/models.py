from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

RequirementCategory = Literal["functional", "non-functional", "constraint", "assumption"]
RequirementConfidence = Literal["high", "medium", "low"]
Priority = Literal["must-have", "should-have", "could-have", "wont-have"]
CoverageStatus = Literal["covered", "uncovered", "no-stories-yet"]


class Requirement(BaseModel):
    id: str = Field(default_factory=lambda: f"REQ-{uuid4().hex[:8].upper()}")
    text: str
    category: RequirementCategory
    confidence: RequirementConfidence = "medium"
    captured_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class UserStory(BaseModel):
    id: str
    title: str
    as_a: str = Field(description="The role or persona.")
    i_want: str = Field(description="The capability or goal.")
    so_that: str = Field(description="The business or user benefit.")
    source_requirement_ids: list[str] = Field(
        description="Stable requirement IDs that produced this story."
    )
    acceptance_criteria: list[str] = Field(default_factory=list)
    priority: Priority
    story_points: int

    @field_validator("source_requirement_ids")
    @classmethod
    def validate_source_requirement_ids(cls, value: list[str]) -> list[str]:
        deduped: list[str] = []
        for requirement_id in value:
            normalized = requirement_id.strip()
            if not normalized:
                raise ValueError("source_requirement_ids cannot include blank IDs")
            if normalized not in deduped:
                deduped.append(normalized)
        return deduped

    @field_validator("story_points")
    @classmethod
    def validate_story_points(cls, value: int) -> int:
        allowed = {1, 2, 3, 5, 8, 13}
        if value not in allowed:
            raise ValueError(f"story_points must be one of {sorted(allowed)}")
        return value


class UserStorySet(BaseModel):
    user_stories: list[UserStory]


class RequirementCoverage(BaseModel):
    """Coverage status for a single requirement."""

    requirement_id: str
    text: str
    category: RequirementCategory
    status: CoverageStatus
    story_ids: list[str] = Field(
        default_factory=list,
        description="IDs of user stories that cite this requirement.",
    )


class CoverageReport(BaseModel):
    """Requirement-to-story coverage analysis for a discovery session."""

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    items: list[RequirementCoverage] = Field(default_factory=list)
    covered_count: int = 0
    uncovered_count: int = 0
    low_confidence_count: int = 0
    coverage_pct: float = 0.0


class SessionSummary(BaseModel):
    """Structured executive summary of a discovery call."""

    overview: str = Field(description="One-paragraph narrative of the session goal and scope.")
    key_requirements: dict[str, list[str]] = Field(
        description="Requirements grouped by category (functional, non-functional, constraint, assumption)."
    )
    open_questions: list[str] = Field(
        description="Topics that were raised but not resolved during the call."
    )
    risks_and_assumptions: list[str] = Field(
        description="Risks inferred from the discussion and explicit assumption-category requirements."
    )


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
    summary: SessionSummary | None = None
    coverage_report: CoverageReport | None = None
