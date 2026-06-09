from __future__ import annotations

import json
import os
from typing import Literal

from openai import OpenAI

from realtime_assistant.memory import memory
from realtime_assistant.models import (
    DiscoverySession,
    Requirement,
    SessionSummary,
    UserStory,
    UserStorySet,
)
from realtime_assistant.prompts import story_generation_prompt


def get_embedding(text: str) -> list[float]:
    """Return an embedding vector for requirement deduplication."""
    client = OpenAI()
    response = client.embeddings.create(model="text-embedding-3-small", input=text)
    return list(response.data[0].embedding)


def validate_story_source_requirement_ids(
    stories: list[UserStory], requirements: list[Requirement]
) -> list[UserStory]:
    """Ensure generated story traceability only references current requirements."""
    valid_ids = [requirement.id for requirement in requirements]
    valid_id_set = set(valid_ids)
    if not valid_ids:
        return [
            story.model_copy(update={"source_requirement_ids": []})
            for story in stories
        ]

    reconciled: list[UserStory] = []
    for story in stories:
        source_ids: list[str] = []
        for requirement_id in story.source_requirement_ids:
            if requirement_id in valid_id_set and requirement_id not in source_ids:
                source_ids.append(requirement_id)
        if not source_ids:
            source_ids = list(valid_ids)
        reconciled.append(story.model_copy(update={"source_requirement_ids": source_ids}))
    return reconciled


def generate_user_stories(requirements: list[Requirement], model: str = "gpt-4o") -> list[UserStory]:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set. Copy .env.example to .env and add a key.")

    client = OpenAI()
    messages = [
        {
            "role": "system",
            "content": "You produce structured Agile user stories for software teams.",
        },
        {"role": "user", "content": story_generation_prompt(requirements)},
    ]

    try:
        completion = client.beta.chat.completions.parse(
            model=model,
            messages=messages,
            response_format=UserStorySet,
        )
        _accumulate_chat_completion_usage(completion)
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise RuntimeError("Structured output parser returned no parsed content.")
        return validate_story_source_requirement_ids(parsed.user_stories, requirements)
    except AttributeError:
        schema = UserStorySet.model_json_schema()
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "user_story_set",
                    "schema": schema,
                    "strict": True,
                },
            },
        )
        _accumulate_chat_completion_usage(completion)
        content = completion.choices[0].message.content
        if content is None:
            raise RuntimeError("Story generation returned no content.")
        parsed = UserStorySet.model_validate(json.loads(content))
        return validate_story_source_requirement_ids(parsed.user_stories, requirements)


def score_requirement_confidence(
    requirement_text: str,
    category: str,
    session: DiscoverySession,
    model: str = "gpt-4o",
) -> Literal["high", "medium", "low"]:
    """Rate how clearly articulated a captured requirement is."""
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set. Copy .env.example to .env and add a key.")

    client = OpenAI()
    nearby_requirements = "\n".join(
        f"- {req.id} [{req.category}, {req.confidence}]: {req.text}"
        for req in session.requirements[-8:]
    )
    messages = [
        {
            "role": "system",
            "content": (
                "You rate requirement clarity for software discovery. "
                "Return exactly one word: high, medium, or low."
            ),
        },
        {
            "role": "user",
            "content": (
                "Rate how clearly articulated this requirement is.\n\n"
                f"Requirement: {requirement_text}\n"
                f"Category: {category}\n\n"
                "Use high when the requirement is specific and testable, medium when it is "
                "understandable but missing some detail, and low when it is vague, ambiguous, "
                "or needs follow-up before story generation.\n\n"
                f"Recent session requirements:\n{nearby_requirements or '(none)'}"
            ),
        },
    ]
    completion = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0,
    )
    content = completion.choices[0].message.content
    score = (content or "").strip().lower()
    if score in {"high", "medium", "low"}:
        return score
    return "medium"


def _summary_prompt(requirements: list[Requirement], clarified_topics: list[str]) -> str:
    req_lines = "\n".join(
        f"- [{req.category}] {req.text}" for req in requirements
    )
    clarified = ", ".join(clarified_topics) if clarified_topics else "none"
    return (
        "You are a senior business analyst. Based on the discovery call data below, "
        "produce a concise executive summary.\n\n"
        f"## Captured Requirements\n{req_lines or '(none)'}\n\n"
        f"## Clarified Topics\n{clarified}\n\n"
        "Fill every field of the SessionSummary schema. "
        "Group requirements by their category label. "
        "List any topics that appear in the requirements but are NOT in clarified topics as open questions. "
        "Identify risks from non-functional / constraint / assumption requirements."
    )


def generate_session_summary(
    requirements: list[Requirement],
    clarified_topics: list[str],
    model: str = "gpt-4o",
) -> SessionSummary:
    """Generate a structured executive summary from captured discovery-call data."""
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set. Copy .env.example to .env and add a key.")

    client = OpenAI()
    messages = [
        {"role": "system", "content": "You are a senior business analyst."},
        {"role": "user", "content": _summary_prompt(requirements, clarified_topics)},
    ]

    try:
        completion = client.beta.chat.completions.parse(
            model=model,
            messages=messages,
            response_format=SessionSummary,
        )
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise RuntimeError("Structured output parser returned no parsed content.")
        return parsed
    except AttributeError:
        schema = SessionSummary.model_json_schema()
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "session_summary",
                    "schema": schema,
                    "strict": True,
                },
            },
        )
        content = completion.choices[0].message.content
        if content is None:
            raise RuntimeError("Summary generation returned no content.")
        return SessionSummary.model_validate(json.loads(content))


def _accumulate_chat_completion_usage(completion: object) -> None:
    usage = getattr(completion, "usage", None)
    if usage is None:
        return
    input_tokens = _usage_value(usage, "input_tokens", "prompt_tokens")
    output_tokens = _usage_value(usage, "output_tokens", "completion_tokens")
    if input_tokens or output_tokens:
        memory.accumulate_chat_usage(input_tokens, output_tokens)


def _usage_value(usage: object, *keys: str) -> int:
    for key in keys:
        if isinstance(usage, dict):
            value = usage.get(key)
        else:
            value = getattr(usage, key, None)
        if isinstance(value, int):
            return value
    return 0
