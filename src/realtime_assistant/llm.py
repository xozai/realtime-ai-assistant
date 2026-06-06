from __future__ import annotations

import json
import os

from openai import OpenAI

from realtime_assistant.models import Requirement, UserStory, UserStorySet
from realtime_assistant.prompts import story_generation_prompt


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
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise RuntimeError("Structured output parser returned no parsed content.")
        return parsed.user_stories
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
        content = completion.choices[0].message.content
        if content is None:
            raise RuntimeError("Story generation returned no content.")
        return UserStorySet.model_validate(json.loads(content)).user_stories
