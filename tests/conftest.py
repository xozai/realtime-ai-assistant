from __future__ import annotations

from types import SimpleNamespace

import pytest

from realtime_assistant.models import DiscoverySession, Requirement, UserStory, UserStorySet


@pytest.fixture
def sample_requirement() -> Requirement:
    return Requirement(
        id="REQ-001",
        text="Users can log in with email",
        category="functional",
    )


@pytest.fixture
def sample_user_story() -> UserStory:
    return UserStory(
        id="US-001",
        title="Email login",
        as_a="registered user",
        i_want="to log in with my email address",
        so_that="I can securely access my account",
        acceptance_criteria=[
            "Given a registered user, when valid credentials are submitted, then access is granted.",
            "Given invalid credentials, when login is attempted, then an error is shown.",
        ],
        priority="must-have",
        story_points=3,
    )


@pytest.fixture
def sample_session(sample_requirement: Requirement, sample_user_story: UserStory) -> DiscoverySession:
    second_requirement = Requirement(
        id="REQ-002",
        text="Users can reset forgotten passwords",
        category="functional",
    )
    second_story = UserStory(
        id="US-002",
        title="Password reset",
        as_a="registered user",
        i_want="to reset my forgotten password",
        so_that="I can regain account access",
        acceptance_criteria=["Given a valid email, when reset is requested, then a reset link is sent."],
        priority="should-have",
        story_points=5,
    )
    return DiscoverySession(
        session_id="DISC-001",
        requirements=[sample_requirement, second_requirement],
        user_stories=[sample_user_story, second_story],
    )


@pytest.fixture
def mock_openai_response() -> SimpleNamespace:
    parsed = UserStorySet(
        user_stories=[
            UserStory(
                id="US-001",
                title="Email login",
                as_a="registered user",
                i_want="to log in with email",
                so_that="I can access my account",
                acceptance_criteria=["Given valid credentials, then the user is logged in."],
                priority="must-have",
                story_points=3,
            ),
            UserStory(
                id="US-002",
                title="Password reset",
                as_a="registered user",
                i_want="to reset my password",
                so_that="I can recover access",
                acceptance_criteria=["Given a valid account, then a reset email is sent."],
                priority="should-have",
                story_points=5,
            ),
        ]
    )
    message = SimpleNamespace(parsed=parsed)
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])
