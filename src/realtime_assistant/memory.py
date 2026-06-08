from __future__ import annotations

from realtime_assistant.models import DiscoverySession, Requirement, RequirementCategory, UserStory

__all__ = ["SessionMemory", "memory"]


class SessionMemory:
    """CRUD-style in-session memory for a single discovery session.

    The assistant keeps one active :class:`DiscoverySession` in memory. Items are
    keyed by their model IDs; adding an item with an existing ID replaces the
    stored item while preserving list order for all other items.
    """

    def __init__(self, session: DiscoverySession | None = None) -> None:
        self.session = session or DiscoverySession()
        self.clarified_topics: set[str] = set()

    def get_current_session(self) -> DiscoverySession:
        """Return the active discovery session."""
        return self.session

    def create_session(self, session: DiscoverySession | None = None) -> DiscoverySession:
        """Start a new active discovery session and clear per-session topic state."""
        self.session = session or DiscoverySession()
        self.clear_clarified_topics()
        return self.session

    def reset_session(self) -> DiscoverySession:
        """Replace the active session with a fresh empty discovery session."""
        return self.create_session()

    def dump_session(self, *, mode: str = "json") -> dict:
        """Serialize the active session for dashboards, tools, or tests."""
        return self.session.model_dump(mode=mode)

    def create_requirement(self, text: str, category: RequirementCategory) -> Requirement:
        """Create and store a requirement from raw text and category."""
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
        """Return stored requirements in insertion order."""
        return list(self.session.requirements)

    def get_all_requirements(self) -> list[Requirement]:
        """Compatibility alias for :meth:`list_requirements`."""
        return self.list_requirements()

    def clear_requirements(self) -> None:
        """Remove all stored requirements from the active session."""
        self.session.requirements.clear()

    def get_requirement(self, requirement_id: str) -> Requirement | None:
        """Return one requirement by ID, or ``None`` when it is not present."""
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

    def remove_requirement(self, requirement_id: str) -> bool:
        """Remove a requirement by ID and report whether anything changed."""
        original_count = len(self.session.requirements)
        self.session.requirements = [
            req for req in self.session.requirements if req.id != requirement_id
        ]
        return len(self.session.requirements) != original_count

    def delete_requirement(self, requirement_id: str) -> bool:
        """Compatibility alias for :meth:`remove_requirement`."""
        return self.remove_requirement(requirement_id)

    def mark_clarified(self, topic: str) -> str:
        """Mark a discovery topic as clarified and return its normalized name."""
        normalized = self._normalize_topic(topic)
        if normalized:
            self.clarified_topics.add(normalized)
        return normalized

    def is_topic_clarified(self, topic: str) -> bool:
        """Return whether a topic has already been marked clarified."""
        return self._normalize_topic(topic) in self.clarified_topics

    def list_clarified_topics(self) -> list[str]:
        """Return clarified topics in deterministic order."""
        return sorted(self.clarified_topics)

    def remove_clarified_topic(self, topic: str) -> bool:
        """Remove a clarified topic and report whether anything changed."""
        normalized = self._normalize_topic(topic)
        if normalized not in self.clarified_topics:
            return False
        self.clarified_topics.remove(normalized)
        return True

    def clear_clarified_topics(self) -> None:
        """Remove all clarified topic markers."""
        self.clarified_topics.clear()

    def set_user_stories(self, stories: list[UserStory]) -> None:
        """Replace all generated user stories for the active session."""
        self.session.user_stories = list(stories)

    def replace_user_stories(self, stories: list[UserStory]) -> None:
        """Compatibility-friendly explicit replacement alias."""
        self.set_user_stories(stories)

    def add_user_story(self, story: UserStory) -> UserStory:
        """Store a user story, overwriting an existing story with the same ID."""
        self.session.user_stories = [
            existing for existing in self.session.user_stories if existing.id != story.id
        ]
        self.session.user_stories.append(story)
        return story

    def list_user_stories(self) -> list[UserStory]:
        """Return generated user stories in insertion order."""
        return list(self.session.user_stories)

    def get_user_story(self, story_id: str) -> UserStory | None:
        """Return one user story by ID, or ``None`` when it is not present."""
        return next((story for story in self.session.user_stories if story.id == story_id), None)

    def remove_user_story(self, story_id: str) -> bool:
        """Remove a user story by ID and report whether anything changed."""
        original_count = len(self.session.user_stories)
        self.session.user_stories = [
            story for story in self.session.user_stories if story.id != story_id
        ]
        return len(self.session.user_stories) != original_count

    def delete_user_story(self, story_id: str) -> bool:
        """Compatibility alias for :meth:`remove_user_story`."""
        return self.remove_user_story(story_id)

    def clear_user_stories(self) -> None:
        """Remove all generated user stories from the active session."""
        self.session.user_stories.clear()

    @staticmethod
    def _normalize_topic(topic: str) -> str:
        return topic.strip().lower()


memory = SessionMemory()
