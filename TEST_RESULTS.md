# Test Results — realtime-ai-assistant

Command run:

```bash
pytest tests/ -v --tb=short
```

## Summary

- Total tests: 32
- Passed: 32
- Failed: 0
- Skipped: 0

## Baseline Failure Before Fixes

- Initial collection failed with `ModuleNotFoundError: No module named 'realtime_assistant'` because the project uses a `src/` layout but pytest did not have `src` on `pythonpath`.
- After source and config fixes, one prompt assertion failed because `SYSTEM_PROMPT` referenced `generate_user_stories` but did not include the plain phrase `user story` or `user stories`. The prompt now includes that wording.

## Final Result

All tests pass:

```text
============================== 32 passed in 0.37s ==============================
```

## Coverage Gaps Identified

- Realtime WebSocket lifecycle is not covered by automated tests; current tests exercise tool handlers directly.
- OpenAI API failures, structured-output parse failures, and fallback Chat Completions behavior are not exhaustively covered.
- CLI interactive behavior and scripted prompt timing are not end-to-end tested.
- Export tests verify content and overwrite behavior, but not filesystem permission failures.
- Logging output is not asserted beyond successful handler execution.
