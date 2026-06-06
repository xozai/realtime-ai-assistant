from __future__ import annotations

from realtime_assistant.models import DiscoverySession, Requirement, RequirementCategory, UserStory


class SessionMemory:
    """CRUD-style in-session memory for requirements and generated stories."""

    def __init__(self) -> None:
        self.session = DiscoverySession()
        self.clarified_topics: set[str] = set()

    def create_requirement(self, text: str, category: RequirementCategory) -> Requirement:
        requirement = Requirement(text=text.strip(), category=category)
        return self.add_requirement(requirement)

    def add_requirement(self, requirement: Requirement) -> Requirement:
        """Store a requirement, overwriting an existing item with the same ID."""
        self.session.requirements = [
            existing for existing in self.session.requirements if existing.id != requirement.id
        ]
        self.session.requirements.append(requirement)
        return requirement

    def list_requirements(self) -> list[Requirement]:
        return list(self.session.requirements)

    def get_all_requirements(self) -> list[Requirement]:
        return self.list_requirements()

    def clear_requirements(self) -> None:
        self.session.requirements.clear()

    def get_requirement(self, requirement_id: str) -> Requirement | None:
        return next((req for req in self.session.requirements if req.id == requirement_id), None)

    def update_requirement(
        self,
        requirement_id: str,
        *,
        text: str | None = None,
        category: RequirementCategory | None = None,
    ) -> Requirement | None:
        requirement = self.get_requirement(requirement_id)
        if requirement is None:
            return None
        if text is not None:
            requirement.text = text.strip()
        if category is not None:
            requirement.category = category
        return requirement

    def delete_requirement(self, requirement_id: str) -> bool:
        original_count = len(self.session.requirements)
        self.session.requirements = [
            req for req in self.session.requirements if req.id != requirement_id
        ]
        return len(self.session.requirements) != original_count

    def mark_clarified(self, topic: str) -> None:
        self.clarified_topics.add(topic.strip().lower())

    def set_user_stories(self, stories: list[UserStory]) -> None:
        self.session.user_stories = stories

    def list_user_stories(self) -> list[UserStory]:
        return list(self.session.user_stories)


memory = SessionMemory()
