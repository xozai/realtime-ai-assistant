from __future__ import annotations

import json
import math
import os
from pathlib import Path

from realtime_assistant.models import (
    DiscoverySession,
    Priority,
    Requirement,
    RequirementCategory,
    StoryRefinementRecord,
    UserStory,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SESSIONS_DIR = PROJECT_ROOT / "sessions"


def _dedup_similarity_threshold() -> float:
    try:
        return float(os.getenv("DEDUP_THRESHOLD", "0.85"))
    except ValueError:
        return 0.85


DEDUP_SIMILARITY_THRESHOLD = _dedup_similarity_threshold()

__all__ = [
    "SESSIONS_DIR",
    "SessionMemory",
    "add_requirement",
    "add_user_story",
    "accumulate_chat_usage",
    "accumulate_embedding_usage",
    "accumulate_realtime_usage",
    "clear_requirements",
    "clear_user_stories",
    "configure_export_options",
    "create_session",
    "delete_requirement",
    "delete_user_story",
    "dump_session",
    "get_all_requirements",
    "get_all_user_stories",
    "get_current_session",
    "get_requirement",
    "get_user_story",
    "cosine_similarity",
    "DEDUP_SIMILARITY_THRESHOLD",
    "find_similar_requirement",
    "list_requirements",
    "list_user_stories",
    "load_session",
    "memory",
    "remove_requirement",
    "remove_user_story",
    "replace_user_story",
    "replace_user_stories",
    "reset_session",
    "save_session",
    "set_user_stories",
    "update_requirement",
    "update_user_story",
]


class SessionMemory:
    """CRUD-style in-session memory for a single discovery session.

    The assistant keeps one active :class:`DiscoverySession` in memory. Items are
    keyed by their model IDs; adding an item with an existing ID replaces the
    stored item while preserving list order for all other items.
    """

    def __init__(
        self,
        session: DiscoverySession | None = None,
        *,
        project_key: str = "default",
    ) -> None:
        self.session = session or DiscoverySession(project_key=project_key)
        self.clarified_topics: set[str] = set()
        self.export_output_dir: Path | None = None
        self.export_name = "user_stories"

    def get_current_session(self) -> DiscoverySession:
        """Return the active discovery session."""
        return self.session

    def create_session(
        self,
        session: DiscoverySession | None = None,
        *,
        project_key: str | None = None,
    ) -> DiscoverySession:
        """Start a new active discovery session and clear per-session topic state."""
        if session is not None and project_key is not None:
            session = session.model_copy(
                update={"project_key": _filename_safe(project_key, "project_key")}
            )
        elif session is None:
            session = DiscoverySession(project_key=project_key or self.session.project_key)
        self.session = session
        self.clear_clarified_topics()
        return self.session

    def configure_export_options(
        self,
        *,
        output_dir: Path | str | None = None,
        export_name: str | None = None,
    ) -> None:
        """Set default export destination options for tool calls in this session."""
        self.export_output_dir = Path(output_dir) if output_dir is not None else None
        self.export_name = export_name or "user_stories"

    def reset_session(self) -> DiscoverySession:
        """Replace the active session with a fresh empty discovery session."""
        return self.create_session()

    def dump_session(self, *, mode: str = "json") -> dict:
        """Serialize the active session for dashboards, tools, or tests."""
        return self.session.model_dump(mode=mode)

    def accumulate_realtime_usage(self, input_tokens: int = 0, output_tokens: int = 0) -> None:
        """Add Realtime token usage to the active session."""
        self._accumulate_usage("realtime", input_tokens, output_tokens)

    def accumulate_chat_usage(self, input_tokens: int = 0, output_tokens: int = 0) -> None:
        """Add Chat Completions token usage to the active session."""
        self._accumulate_usage("chat_completions", input_tokens, output_tokens)

    def accumulate_embedding_usage(self, input_tokens: int = 0, output_tokens: int = 0) -> None:
        """Add embedding token usage to the active session."""
        self._accumulate_usage("embeddings", input_tokens, output_tokens)

    def _accumulate_usage(self, model_type: str, input_tokens: int, output_tokens: int) -> None:
        usage = getattr(self.session.costs, model_type)
        updated = usage.model_copy(
            update={
                "input_tokens": usage.input_tokens + max(0, input_tokens),
                "output_tokens": usage.output_tokens + max(0, output_tokens),
            }
        )
        costs = self.session.costs.model_copy(update={model_type: updated})
        self.session = self.session.model_copy(update={"costs": costs})

    def dump_persisted_session(self) -> dict:
        """Serialize session memory to the stable on-disk JSON shape."""
        return {
            "session": self.session.model_dump(mode="json"),
            "clarified_topics": self.list_clarified_topics(),
        }

    def save_session(
        self,
        output_dir: Path | str = SESSIONS_DIR,
        *,
        project_key: str | None = None,
    ) -> Path:
        """Persist the active discovery session and clarified topic markers."""
        if project_key is not None:
            self.session = self.session.model_copy(
                update={"project_key": _filename_safe(project_key, "project_key")}
            )
        path = self._session_path(
            self.session.session_id,
            output_dir,
            project_key=self.session.project_key,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = self.dump_persisted_session()
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return path

    def load_session(
        self,
        session_id: str,
        input_dir: Path | str = SESSIONS_DIR,
        *,
        project_key: str | None = None,
    ) -> DiscoverySession:
        """Load a persisted discovery session and make it active."""
        resolved_project_key = project_key or self.session.project_key
        path = self._session_path(session_id, input_dir, project_key=resolved_project_key)
        if not path.exists():
            legacy_path = self._legacy_session_path(session_id, input_dir)
            if legacy_path.exists():
                path = legacy_path
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Session file {path} must contain a JSON object.")

        session_payload = payload.get("session")
        if not isinstance(session_payload, dict):
            raise ValueError(f"Session file {path} is missing a session object.")

        session = DiscoverySession.model_validate(session_payload)
        if project_key is not None:
            session = session.model_copy(
                update={"project_key": _filename_safe(project_key, "project_key")}
            )
        clarified_topics = payload.get("clarified_topics", [])
        if not isinstance(clarified_topics, list):
            raise ValueError(f"Session file {path} has invalid clarified_topics.")

        self.create_session(session)
        for topic in clarified_topics:
            if not isinstance(topic, str):
                raise ValueError(f"Session file {path} has a non-string clarified topic.")
            self.mark_clarified(topic)
        return self.session

    @staticmethod
    def _session_path(
        session_id: str,
        directory: Path | str,
        *,
        project_key: str = "default",
    ) -> Path:
        normalized_session_id = _filename_safe(session_id, "session_id")
        normalized_project_key = _filename_safe(project_key, "project_key")
        return Path(directory) / normalized_project_key / f"{normalized_session_id}.json"

    @staticmethod
    def _legacy_session_path(session_id: str, directory: Path | str) -> Path:
        normalized_session_id = _filename_safe(session_id, "session_id")
        return Path(directory) / f"{normalized_session_id}.json"

    def create_requirement(self, text: str, category: RequirementCategory) -> Requirement:
        """Create and store a requirement from raw text and category."""
        requirement = Requirement(text=text.strip(), category=category)
        return self.add_requirement(requirement)

    def find_similar_requirement(
        self,
        embedding: list[float],
        threshold: float = DEDUP_SIMILARITY_THRESHOLD,
    ) -> Requirement | None:
        """Return the first stored requirement whose embedding meets the threshold."""
        for requirement in self.session.requirements:
            if requirement.embedding is None:
                continue
            if cosine_similarity(embedding, requirement.embedding) >= threshold:
                return requirement
        return None

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
        requirement_index = self._requirement_index(requirement_id)
        if requirement_index is None:
            return None

        requirement = self.session.requirements[requirement_index]
        data = requirement.model_dump()
        if text is not None:
            data["text"] = text.strip()
        if category is not None:
            data["category"] = category
        updated = Requirement.model_validate(data)
        self.session.requirements[requirement_index] = updated
        return updated

    def _requirement_index(self, requirement_id: str) -> int | None:
        for index, requirement in enumerate(self.session.requirements):
            if requirement.id == requirement_id:
                return index
        return None

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

    def get_all_user_stories(self) -> list[UserStory]:
        """Compatibility alias for :meth:`list_user_stories`."""
        return self.list_user_stories()

    def get_user_story(self, story_id: str) -> UserStory | None:
        """Return one user story by ID, or ``None`` when it is not present."""
        return next((story for story in self.session.user_stories if story.id == story_id), None)

    def update_user_story(
        self,
        story_id: str,
        *,
        title: str | None = None,
        as_a: str | None = None,
        i_want: str | None = None,
        so_that: str | None = None,
        acceptance_criteria: list[str] | None = None,
        priority: Priority | None = None,
        story_points: int | None = None,
    ) -> UserStory | None:
        """Update a stored user story by ID and return the updated story."""
        story_index = self._user_story_index(story_id)
        if story_index is None:
            return None

        story = self.session.user_stories[story_index]
        data = story.model_dump()
        updates = {
            "title": title,
            "as_a": as_a,
            "i_want": i_want,
            "so_that": so_that,
            "acceptance_criteria": acceptance_criteria,
            "priority": priority,
            "story_points": story_points,
        }
        data.update({key: value for key, value in updates.items() if value is not None})
        updated = UserStory.model_validate(data)
        self.session.user_stories[story_index] = updated
        return updated

    def replace_user_story(
        self,
        story_id: str,
        replacement: UserStory,
        *,
        feedback: str | None = None,
        requirement_ids: list[str] | None = None,
    ) -> UserStory | None:
        """Replace one generated story, preserving list order and recording history."""
        story_index = self._user_story_index(story_id)
        if story_index is None:
            return None

        previous = self.session.user_stories[story_index]
        updated = replacement.model_copy(update={"id": previous.id})
        self.session.user_stories[story_index] = updated
        self.session.story_refinement_history.append(
            StoryRefinementRecord(
                story_id=previous.id,
                previous_story=previous,
                replacement_story=updated,
                feedback=feedback.strip() if feedback else None,
                requirement_ids=list(requirement_ids or []),
            )
        )
        return updated

    def _user_story_index(self, story_id: str) -> int | None:
        for index, story in enumerate(self.session.user_stories):
            if story.id == story_id:
                return index
        return None

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


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity without third-party numeric dependencies."""
    if not a or not b or len(a) != len(b):
        return 0.0

    dot_product = sum(left * right for left, right in zip(a, b, strict=True))
    magnitude_a = math.sqrt(sum(value * value for value in a))
    magnitude_b = math.sqrt(sum(value * value for value in b))
    if magnitude_a == 0.0 or magnitude_b == 0.0:
        return 0.0
    return dot_product / (magnitude_a * magnitude_b)


def _filename_safe(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be blank.")
    if Path(normalized).name != normalized:
        raise ValueError(f"{field_name} must be a filename-safe value, not a path.")
    return normalized


memory = SessionMemory()


def get_current_session() -> DiscoverySession:
    """Return the active singleton discovery session."""
    return memory.get_current_session()


def create_session(
    session: DiscoverySession | None = None,
    *,
    project_key: str | None = None,
) -> DiscoverySession:
    """Start a new singleton discovery session."""
    return memory.create_session(session, project_key=project_key)


def reset_session() -> DiscoverySession:
    """Reset the singleton discovery session."""
    return memory.reset_session()


def dump_session(*, mode: str = "json") -> dict:
    """Serialize the active singleton discovery session."""
    return memory.dump_session(mode=mode)


def accumulate_realtime_usage(input_tokens: int = 0, output_tokens: int = 0) -> None:
    """Add Realtime token usage to the singleton session."""
    memory.accumulate_realtime_usage(input_tokens, output_tokens)


def accumulate_chat_usage(input_tokens: int = 0, output_tokens: int = 0) -> None:
    """Add Chat Completions token usage to the singleton session."""
    memory.accumulate_chat_usage(input_tokens, output_tokens)


def accumulate_embedding_usage(input_tokens: int = 0, output_tokens: int = 0) -> None:
    """Add embedding token usage to the singleton session."""
    memory.accumulate_embedding_usage(input_tokens, output_tokens)


def save_session(
    output_dir: Path | str = SESSIONS_DIR,
    *,
    project_key: str | None = None,
) -> Path:
    """Persist the active singleton discovery session."""
    return memory.save_session(output_dir, project_key=project_key)


def load_session(
    session_id: str,
    input_dir: Path | str = SESSIONS_DIR,
    *,
    project_key: str | None = None,
) -> DiscoverySession:
    """Load a persisted discovery session into singleton memory."""
    return memory.load_session(session_id, input_dir, project_key=project_key)


def add_requirement(requirement: Requirement) -> Requirement:
    """Store a requirement in the singleton session."""
    return memory.add_requirement(requirement)


def list_requirements() -> list[Requirement]:
    """Return all requirements from the singleton session."""
    return memory.list_requirements()


def get_all_requirements() -> list[Requirement]:
    """Return all requirements from the singleton session."""
    return memory.get_all_requirements()


def get_requirement(requirement_id: str) -> Requirement | None:
    """Return one singleton requirement by ID."""
    return memory.get_requirement(requirement_id)


def find_similar_requirement(
    embedding: list[float],
    threshold: float = DEDUP_SIMILARITY_THRESHOLD,
) -> Requirement | None:
    """Return a singleton requirement with an embedding above the threshold."""
    return memory.find_similar_requirement(embedding, threshold)


def update_requirement(
    requirement_id: str,
    *,
    text: str | None = None,
    category: RequirementCategory | None = None,
) -> Requirement | None:
    """Update one singleton requirement by ID."""
    return memory.update_requirement(requirement_id, text=text, category=category)


def remove_requirement(requirement_id: str) -> bool:
    """Remove one singleton requirement by ID."""
    return memory.remove_requirement(requirement_id)


def delete_requirement(requirement_id: str) -> bool:
    """Compatibility alias for :func:`remove_requirement`."""
    return remove_requirement(requirement_id)


def clear_requirements() -> None:
    """Remove all singleton requirements."""
    memory.clear_requirements()


def set_user_stories(stories: list[UserStory]) -> None:
    """Replace all singleton user stories."""
    memory.set_user_stories(stories)


def replace_user_stories(stories: list[UserStory]) -> None:
    """Compatibility alias for :func:`set_user_stories`."""
    memory.replace_user_stories(stories)


def add_user_story(story: UserStory) -> UserStory:
    """Store a user story in the singleton session."""
    return memory.add_user_story(story)


def list_user_stories() -> list[UserStory]:
    """Return all user stories from the singleton session."""
    return memory.list_user_stories()


def get_all_user_stories() -> list[UserStory]:
    """Return all user stories from the singleton session."""
    return memory.get_all_user_stories()


def get_user_story(story_id: str) -> UserStory | None:
    """Return one singleton user story by ID."""
    return memory.get_user_story(story_id)


def update_user_story(
    story_id: str,
    *,
    title: str | None = None,
    as_a: str | None = None,
    i_want: str | None = None,
    so_that: str | None = None,
    acceptance_criteria: list[str] | None = None,
    priority: Priority | None = None,
    story_points: int | None = None,
) -> UserStory | None:
    """Update one singleton user story by ID."""
    return memory.update_user_story(
        story_id,
        title=title,
        as_a=as_a,
        i_want=i_want,
        so_that=so_that,
        acceptance_criteria=acceptance_criteria,
        priority=priority,
        story_points=story_points,
    )


def replace_user_story(
    story_id: str,
    replacement: UserStory,
    *,
    feedback: str | None = None,
    requirement_ids: list[str] | None = None,
) -> UserStory | None:
    """Replace one singleton user story while preserving unrelated stories."""
    return memory.replace_user_story(
        story_id,
        replacement,
        feedback=feedback,
        requirement_ids=requirement_ids,
    )


def remove_user_story(story_id: str) -> bool:
    """Remove one singleton user story by ID."""
    return memory.remove_user_story(story_id)


def delete_user_story(story_id: str) -> bool:
    """Compatibility alias for :func:`remove_user_story`."""
    return remove_user_story(story_id)


def clear_user_stories() -> None:
    """Remove all singleton user stories."""
    memory.clear_user_stories()


def configure_export_options(
    *,
    output_dir: Path | str | None = None,
    export_name: str | None = None,
) -> None:
    """Set singleton export destination options."""
    memory.configure_export_options(output_dir=output_dir, export_name=export_name)
