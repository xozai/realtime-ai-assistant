# Code Review — realtime-ai-assistant

## Files Reviewed

- `src/realtime_assistant/main.py`
- `src/realtime_assistant/tools.py`
- `src/realtime_assistant/models.py`
- `src/realtime_assistant/llm.py`
- `src/realtime_assistant/memory.py`
- `src/realtime_assistant/prompts.py`
- `src/realtime_assistant/export.py`
- `src/realtime_assistant/logging.py`

## Issues Found

### Critical

- None found. The package imports are present, the entry point exists, and `OPENAI_API_KEY` is loaded from environment after `load_dotenv()` rather than hardcoded.

### Major

- `memory.py`: The memory API requested by the test plan is incomplete. There are no `add_requirement`, `get_all_requirements`, or `clear_requirements` methods, so tests and external callers cannot use the expected store interface.
- `export.py`: The module only exposes `export_user_stories`; it does not expose `export_to_json` or `export_to_markdown`, which are needed for direct unit testing and clearer public API boundaries.
- `prompts.py`: There is no `STORY_GENERATION_PROMPT` constant or direct equivalent export, only the `story_generation_prompt()` function. This makes prompt presence difficult to assert directly.
- `main.py`: WebSocket receive events call `json.loads(raw_event)` without guarding malformed frames. API error events are logged, but malformed payloads or unexpected event shape can terminate the receiver.
- `main.py`: Pending sender/receiver tasks are cancelled but not awaited with `return_exceptions=True`, so cancellation cleanup can be noisy and incomplete.
- `main.py`: Scripted sessions return immediately after sending prompts, which can cause the receiver task to be cancelled before all model/tool responses are processed.
- `tools.py`: Tool handler results are mostly JSON-safe dicts, but there is no central serializer in the dispatch path. If a handler returns Pydantic objects in the future, `json.dumps()` in `main.py` will fail.

### Minor

- `main.py`: The session config includes `voice` and `input_audio_transcription` even though `modalities` is `["text"]`. This is harmless but confusing for a text-only CLI flow.
- `main.py`: The CLI help says `done` generates stories, but `send_user_input()` only exits on `quit` or `exit`; story generation depends on model behavior.
- `llm.py`: The OpenAI model default is fixed to `gpt-4o`; it would be easier to test and operate if configurable through environment or CLI.
- `memory.py`: Duplicate requirement IDs are not explicitly rejected or merged. Current list-based behavior allows duplicates.
- `logging.py`: `configure_logging()` runs at import time, which can make test output noisier.

## What Is Working Correctly

- Pydantic models are used for `Requirement`, `UserStory`, `UserStorySet`, and `DiscoverySession`.
- `UserStory.story_points` already validates Fibonacci values: `1, 2, 3, 5, 8, 13`.
- Requirement category and priority values are typed with `Literal`, so invalid values raise Pydantic validation errors.
- `Requirement.captured_at` and `DiscoverySession.started_at` default to timezone-aware current timestamps.
- All five Realtime tools are registered with `type`, `name`, `description`, and `parameters`.
- Tool schemas use object parameters, required fields where needed, enums for constrained values, and `additionalProperties: False`.
- Tool dispatch catches unknown tool names, invalid JSON arguments, and handler exceptions.
- Export output is deterministic and overwrites `user_stories.json` and `user_stories.md` cleanly.
- Secrets are not hardcoded; `OPENAI_API_KEY` is read from `.env`/environment.

## What Needs Fixing Before Tests Can Run Reliably

- Add the expected public memory methods and document duplicate ID behavior.
- Add direct `export_to_json()` and `export_to_markdown()` functions.
- Add a direct story generation prompt constant or alias.
- Add a JSON-safe tool result serializer for dispatch or WebSocket output.
- Add pytest tests and fixtures under `tests/`.
- Install or make available test dependencies such as `pytest`.
