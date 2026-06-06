# MVP Roadmap — realtime-ai-assistant

## Current State

The assistant has a working Python package structure, Realtime API session setup, five registered tools, in-session requirement and story memory, structured Pydantic models, JSON/Markdown export, and a pytest suite covering models, memory, exports, prompts, and tool handlers. The current automated suite passes with 32 tests.

## MVP Definition

The MVP is a reliable discovery-call assistant that can capture requirements during a live or scripted session, generate implementation-ready Agile user stories, export them, and hand them off to the team system of record with enough traceability that a product manager can use the output without manual reformatting.

## Feature Backlog

### 1. Voice Input Mode

- Feature name: Voice Input Mode
- Why it is needed for MVP: Live discovery calls need microphone input so the assistant can participate without requiring typed prompts.
- Suggested implementation approach: Add a `--voice` mode using `sounddevice` or `pyaudio`, stream PCM audio frames to the Realtime API, and gate dependencies behind an optional install extra.
- Estimated complexity: L
- Priority: P2 should-have

### 2. Conversation Transcript

- Feature name: Conversation Transcript
- Why it is needed for MVP: Teams need an audit trail from raw conversation to requirement and story output.
- Suggested implementation approach: Add a transcript writer that appends user messages, assistant text, tool calls, and tool results to `transcripts/YYYY-MM-DD_HH-MM-SS.txt`.
- Estimated complexity: M
- Priority: P1 must-have

### 3. Session Resume

- Feature name: Session Resume
- Why it is needed for MVP: Discovery often spans multiple conversations, and users should not lose captured requirements.
- Suggested implementation approach: Persist `DiscoverySession` as JSON, add `--session-id` and `--resume` CLI flags, and hydrate memory from disk before connecting.
- Estimated complexity: M
- Priority: P2 should-have

### 4. Multi-Product Support

- Feature name: Multi-Product Support
- Why it is needed for MVP: Agencies and product teams run discovery across multiple projects and need separate context.
- Suggested implementation approach: Add a project key/name to `DiscoverySession`, store sessions under `sessions/{project_key}/`, and require project selection in CLI/Web UI.
- Estimated complexity: M
- Priority: P2 should-have

### 5. Jira MCP Integration

- Feature name: Jira MCP Integration
- Why it is needed for MVP: Jira handoff is the key value path from discovery to delivery planning.
- Suggested implementation approach: Add `submit_stories_to_jira(project_key: str)` as a new tool. Use a Jira MCP server such as `mcp-atlassian` to create one Jira Story issue per `UserStory`. Map `title` to Summary; combine `as_a`, `i_want`, `so_that`, and acceptance criteria into Description; map story points and priority through configurable fields. Add `JIRA_BASE_URL`, `JIRA_USER_EMAIL`, and `JIRA_API_TOKEN` to `.env.example`, plus a `JiraConfig` Pydantic model. Return created issue keys such as `PROJ-123`.
- Estimated complexity: L
- Priority: P1 must-have

### 6. Slack/Teams Notification

- Feature name: Slack/Teams Notification
- Why it is needed for MVP: Teams need a lightweight notification when stories are generated or exported.
- Suggested implementation approach: Add a notification abstraction with Slack webhook first, then Teams webhook support. Post summary counts, file paths, and Jira issue keys when available.
- Estimated complexity: M
- Priority: P3 nice-to-have

### 7. Web UI Dashboard

- Feature name: Web UI Dashboard
- Why it is needed for MVP: A visual dashboard makes captured requirements and generated stories reviewable during the call.
- Suggested implementation approach: Add FastAPI endpoints around memory/session state and a minimal HTML dashboard showing live requirements, story cards, export buttons, and Jira submission.
- Estimated complexity: L
- Priority: P1 must-have

### 8. Confidence Scoring

- Feature name: Confidence Scoring
- Why it is needed for MVP: Low-confidence requirements need follow-up before engineering commits to implementation.
- Suggested implementation approach: Add `confidence: Literal["high", "medium", "low"]` to `Requirement`, ask the LLM to score each captured item, and surface low-confidence items in summaries.
- Estimated complexity: M
- Priority: P2 should-have

### 9. Requirement Deduplication

- Feature name: Requirement Deduplication
- Why it is needed for MVP: Discovery conversations repeat ideas, and duplicate requirements create duplicate stories.
- Suggested implementation approach: Generate embeddings with `text-embedding-3-small`, compare new requirements against existing items, and ask the user/model whether to merge when similarity exceeds a threshold.
- Estimated complexity: M
- Priority: P2 should-have

### 10. Export to Confluence

- Feature name: Export to Confluence
- Why it is needed for MVP: Product teams often need discovery summaries and story drafts in Confluence as durable documentation.
- Suggested implementation approach: Use the Atlassian MCP server to create or update a Confluence page containing requirements, stories, acceptance criteria, and links to Jira issues.
- Estimated complexity: M
- Priority: P3 nice-to-have
