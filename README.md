# Realtime AI Assistant

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Python 3.11+ realtime AI assistant for software discovery calls. It opens an OpenAI Realtime API WebSocket session, guides a requirements conversation, captures requirements through tool calls, and generates Agile user stories with Pydantic structured output.

Inspired by [`disler/poc-realtime-ai-assistant`](https://github.com/disler/poc-realtime-ai-assistant) — reuses its async Realtime API event loop, tool-chaining pattern, Rich terminal logs, in-session memory, and structured LLM parsing.

---

## Features

| Feature | Status |
|---|---|
| Realtime API discovery assistant (text) | ✅ Shipped |
| Structured user-story generation (Pydantic) | ✅ Shipped |
| JSON + Markdown export | ✅ Shipped |
| Jira integration (`submit_stories_to_jira`) | ✅ Shipped |
| Voice input mode (`--voice`, server VAD) | ✅ Shipped |
| Web dashboard (FastAPI, dark theme, live refresh) | ✅ Shipped |
| Conversation transcript | 🔜 [#1](https://github.com/xozai/realtime-ai-assistant/issues/1) P1 |
| Session resume | ✅ Shipped |
| Multi-product support | 🔜 [#3](https://github.com/xozai/realtime-ai-assistant/issues/3) P2 |
| Confidence scoring | 🔜 [#4](https://github.com/xozai/realtime-ai-assistant/issues/4) P2 |
| Requirement deduplication (embeddings) | 🔜 [#5](https://github.com/xozai/realtime-ai-assistant/issues/5) P2 |
| Slack / Teams notifications | 🔜 [#6](https://github.com/xozai/realtime-ai-assistant/issues/6) P3 |
| Export to Confluence | 🔜 [#7](https://github.com/xozai/realtime-ai-assistant/issues/7) P3 |

---

## Install

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

```bash
OPENAI_API_KEY=your_key_here
```

---

## Run

### Text mode (default)

```bash
python src/realtime_assistant/main.py
```

The web dashboard starts automatically at **http://localhost:8000**. Type messages at the prompt. Type `quit` or `exit` to end the session.

### Voice mode

```bash
pip install sounddevice   # one-time; requires a working microphone
python src/realtime_assistant/main.py --voice
```

Streams PCM16 mono audio at 24 kHz to the Realtime API. Server-side VAD detects end of speech.

### Scripted session

```bash
python src/realtime_assistant/main.py --prompts "We need a task manager|Users need tasks and reminders|Generate stories"
```

---

## CLI Flags

| Flag | Default | Description |
|---|---|---|
| `--voice` | off | Live microphone input (requires `sounddevice`) |
| `--no-dashboard` | off | Disable the web dashboard |
| `--dashboard-port PORT` | `8000` | Dashboard port |
| `--resume SESSION_ID` | unset | Load `sessions/SESSION_ID.json` before connecting |
| `--session-id SESSION_ID` | generated | Start a new session with a known ID |
| `--output-dir PATH` | `exports/` | Directory for generated JSON and Markdown exports |
| `--export-name NAME` | `user_stories` | Base filename for generated exports, without extension |

---

## Web Dashboard

The FastAPI dashboard runs in the same process and shows live requirements and user stories with a dark-theme two-panel layout. Auto-refreshes every 3 seconds.

Open: **http://localhost:8000**

```bash
# Disable
python src/realtime_assistant/main.py --no-dashboard

# Custom port
python src/realtime_assistant/main.py --dashboard-port 9000
```

### Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Inline dark-theme SPA |
| `GET` | `/api/requirements` | All captured requirements |
| `GET` | `/api/stories` | All generated user stories |
| `GET` | `/api/session` | Session ID, start time, counts |
| `POST` | `/api/export` | Export stories to JSON + Markdown |
| `POST` | `/api/jira/{project_key}` | Submit stories to Jira |

The dashboard has **Export** and **Submit to Jira** buttons that call these endpoints directly from the browser.

---

## Tool Chain

The Realtime session registers these tools with the model:

| Tool | Description |
|---|---|
| `capture_requirement(requirement, category)` | Store a requirement in session memory |
| `ask_clarifying_question(topic, question)` | Log a clarifying question |
| `summarize_requirements()` | Print all captured requirements to terminal |
| `generate_user_stories()` | Produce structured `UserStory` objects via Chat Completions |
| `export_user_stories(format, output_dir, export_name)` | Write JSON and Markdown exports; destination fields are optional |
| `submit_stories_to_jira(project_key)` | Create Jira Story issues for each story |

When the model calls a tool, `main.py` receives the function-call event, dispatches it through `dispatch_tool` in `tools.py`, writes the result back to the conversation, and asks the model to continue.

**Requirement categories:** `functional` · `non-functional` · `constraint` · `assumption`

**Story priorities:** `must-have` · `should-have` · `could-have` · `wont-have`

**Story points:** Fibonacci — `1, 2, 3, 5, 8, 13` (Pydantic-validated)

---

## Jira Integration

Submits generated stories to Jira as Story issues via the Atlassian REST API v3. Uses stdlib `urllib` — no extra dependencies.

Add to `.env`:

```bash
JIRA_BASE_URL=https://your-org.atlassian.net
JIRA_USER_EMAIL=you@example.com
JIRA_API_TOKEN=your_api_token_here
JIRA_STORY_POINTS_FIELD=story_points   # or customfield_10016
```

Get a Jira API token at https://id.atlassian.com/manage-profile/security/api-tokens.

### Priority mapping

| Story priority | Jira priority |
|---|---|
| `must-have` | Highest |
| `should-have` | High |
| `could-have` | Medium |
| `wont-have` | Low |

### Example dialogue

```text
User:      Submit these stories to Jira project MYAPP.
Assistant: Submitted 4 stories: MYAPP-101, MYAPP-102, MYAPP-103, MYAPP-104.
```

---

## Voice Input Mode

```bash
pip install sounddevice
python src/realtime_assistant/main.py --voice
```

- Streams PCM16 mono at 24 kHz to the Realtime API
- Server-side VAD (`server_vad`) handles turn detection automatically
- Session config switches to `modalities: ["text", "audio"]` and injects a voice-mode system prompt
- Text mode remains the default — `sounddevice` is only imported when `--voice` is passed

---

## Example Session Transcript

```
Assistant: Hi! I'll help turn this discovery call into implementation-ready user stories.
           What problem are you trying to solve?

User: We need a task manager for small teams — create tasks, organize by project, get reminders.

[Requirement Captured] REQ-4A12C9E0 · functional
  Users can create tasks for small-team work.

[Requirement Captured] REQ-19B2D33F · functional
  Users can organize tasks by project.

[Requirement Captured] REQ-80BA912A · functional
  Users receive reminders for upcoming task deadlines.
Assistant: What should collaboration look like?

User: Project owners can invite teammates by email.

[Requirement Captured] REQ-1D88F20A - functional
  Project owners can invite teammates to shared projects by email.

User: Generate stories.

[Generated User Stories]
US-001  Create Personal Tasks              must-have    3 pts
US-002  Organize Tasks By Project          should-have  5 pts
US-003  Receive Due Date Reminders         must-have    5 pts
US-004  Share A Project With Collaborators could-have   8 pts
```

---

## Sample Output

Pre-populated fictional sample output lives at `user_stories.md` and `user_stories.json`.
Generated exports are written to `exports/<session_id>/user_stories.json` and
`exports/<session_id>/user_stories.md` by default, so normal sessions do not
overwrite the root sample files. Use `--output-dir PATH` to choose another
export directory and `--export-name NAME` to choose a different base filename.

For example:

```bash
python src/realtime_assistant/main.py --session-id DISC-001 --output-dir ./artifacts --export-name backlog
```

Exporting both formats in that session creates `artifacts/DISC-001/backlog.json`
and `artifacts/DISC-001/backlog.md`.
A generated Markdown story looks like:

```markdown
## US-001: Create Personal Tasks

**Priority:** must-have
**Story Points:** 3

**As a** busy professional,
**I want** to create tasks with a title, description, due date, and priority,
**so that** I can capture work quickly and organize what needs to be done.

### Acceptance Criteria

- Users can create a task with title, optional description, due date, and priority.
- The title is required before a task can be saved.
- Newly created tasks appear immediately in the active task list.
```

---

## Project Structure

```text
realtime-ai-assistant/
├── README.md
├── REVIEW.md                    # code review findings
├── TEST_RESULTS.md              # test run summary
├── MVP_ROADMAP.md               # 10-feature MVP roadmap
├── .env.example
├── requirements.txt
├── pyproject.toml
├── user_stories.json            # sample output
├── user_stories.md              # sample output
├── src/
│   └── realtime_assistant/
│       ├── main.py              # async entry point, WebSocket loop, CLI flags
│       ├── tools.py             # tool definitions, handlers, dispatch map
│       ├── models.py            # Pydantic models (Requirement, UserStory, JiraConfig...)
│       ├── llm.py               # structured output + story generation
│       ├── memory.py            # SessionMemory CRUD
│       ├── prompts.py           # SYSTEM_PROMPT, VOICE_MODE_INTRO, story prompt
│       ├── export.py            # JSON + Markdown export
│       ├── jira_client.py       # JiraClient (stdlib urllib, no extra deps)
│       ├── audio.py             # MicrophoneStream for --voice mode
│       ├── dashboard.py         # FastAPI app + inline HTML/CSS/JS SPA
│       ├── server.py            # uvicorn async task wrapper
│       └── logging.py           # Rich logger config
└── tests/
    ├── conftest.py
    ├── test_models.py
    ├── test_memory.py
    ├── test_export.py
    ├── test_tools.py
    ├── test_prompts.py
    ├── test_jira_client.py
    ├── test_tool_jira.py
    ├── test_audio.py
    ├── test_voice_mode.py
    └── test_dashboard.py
```

---

## Tests

The project ships with a full pytest suite (60 tests) covering models, memory,
export, tool handlers, Jira client, voice mode, and the dashboard.

```bash
pip install pytest pytest-asyncio fastapi httpx uvicorn
pytest tests/ -v
```

| Test file | What it covers |
|---|---|
| `test_models.py` | Pydantic validation, Fibonacci points, category/priority literals |
| `test_memory.py` | SessionMemory CRUD, duplicate ID handling |
| `test_export.py` | JSON + Markdown export, overwrite behavior |
| `test_tools.py` | Tool handler functions (mocked OpenAI) |
| `test_prompts.py` | SYSTEM_PROMPT content assertions |
| `test_jira_client.py` | JiraClient HTTP (mocked), priority mapping, description format |
| `test_tool_jira.py` | submit_stories_to_jira handler (mocked), error cases |
| `test_audio.py` | MicrophoneStream (sounddevice fully mocked) |
| `test_voice_mode.py` | Voice session config, voice_sender encoding, --voice wiring |
| `test_dashboard.py` | FastAPI endpoints via TestClient |

**Current count: 60 passing, 0 failures.**

---

## Repo Docs

| File | Description |
|---|---|
| `REVIEW.md` | Code review findings (critical / major / minor severity) |
| `TEST_RESULTS.md` | Test run summary — baseline failures found and fixed |
| `MVP_ROADMAP.md` | 10-feature roadmap with complexity, priority, implementation notes |

---

## MVP Roadmap

Open issues tracking upcoming features:

| # | Feature | Priority |
|---|---|---|
| [#1](https://github.com/xozai/realtime-ai-assistant/issues/1) | Conversation Transcript | P1 |
| [#2](https://github.com/xozai/realtime-ai-assistant/issues/2) | Session Resume | P2 |
| [#3](https://github.com/xozai/realtime-ai-assistant/issues/3) | Multi-Product Support | P2 |
| [#4](https://github.com/xozai/realtime-ai-assistant/issues/4) | Confidence Scoring | P2 |
| [#5](https://github.com/xozai/realtime-ai-assistant/issues/5) | Requirement Deduplication | P2 |
| [#6](https://github.com/xozai/realtime-ai-assistant/issues/6) | Slack / Teams Notifications | P3 |
| [#7](https://github.com/xozai/realtime-ai-assistant/issues/7) | Export to Confluence | P3 |

---

## License

MIT — see [LICENSE](LICENSE) for the full text.

All dependencies (`openai`, `pydantic`, `fastapi`, `rich`, `websockets`, `uvicorn`, `httpx`, `sounddevice`, `python-dotenv`) use permissive licenses (MIT, Apache 2.0, BSD-3). No copyleft dependencies.

---

## Notes

- `generate_user_stories` uses Pydantic structured output via `client.beta.chat.completions.parse` with a JSON-schema fallback for compatible OpenAI client versions.
- Jira submission uses stdlib `urllib` only — no `requests` or `httpx` required in the core app.
- The dashboard runs in the same async event loop via a non-blocking `asyncio.create_task` wrapping `uvicorn.Server`.
- `sounddevice` is only imported inside the voice code path — the app starts fine without it when not using `--voice`.
- No credentials are hardcoded. All secrets are read from `.env` via `python-dotenv`.
