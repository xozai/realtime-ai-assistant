# Realtime AI Assistant

A Python 3.11+ realtime AI assistant for software discovery calls. It opens an OpenAI Realtime API WebSocket session, guides a requirements conversation, captures requirements through tool calls, and generates Agile user stories with Pydantic structured output.

This project follows the core patterns from [`disler/poc-realtime-ai-assistant`](https://github.com/disler/poc-realtime-ai-assistant): an async Realtime API event loop, registered tool schemas plus a function dispatch map, Rich terminal logs, in-session memory, and structured LLM parsing.

## What It Does

- Runs a concise discovery-call assistant over the OpenAI Realtime API.
- Captures requirements during the conversation with `capture_requirement`.
- Tracks clarifying questions with `ask_clarifying_question`.
- Prints captured requirements with `summarize_requirements`.
- Generates structured `UserStory` objects with OpenAI Chat Completions and Pydantic.
- Exports generated stories to `user_stories.json` and `user_stories.md` in the project root.

## Install

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

```bash
OPENAI_API_KEY=your_real_key_here
```

## Run

```bash
python src/realtime_assistant/main.py
```

The web dashboard starts by default at http://localhost:8000.

You can also run a scripted text session:

```bash
python src/realtime_assistant/main.py --prompts "We need a task manager app|Users need tasks, projects, reminders, and sharing|Generate stories"
```

## Web Dashboard

The FastAPI dashboard runs in the same process as the realtime assistant and
shows live requirements and generated user stories during a discovery session.
It uses an inline dark-theme single-page UI with automatic refresh every few
seconds.

Open the dashboard:

```text
http://localhost:8000
```

Disable it when you only want the terminal assistant:

```bash
python src/realtime_assistant/main.py --no-dashboard
```

Run it on another port:

```bash
python src/realtime_assistant/main.py --dashboard-port 8080
```

Dashboard endpoints:

- `GET /` - inline HTML dashboard
- `GET /api/requirements` - captured requirements
- `GET /api/stories` - generated user stories
- `GET /api/session` - session ID, start time, and counts
- `POST /api/export` - export user stories to JSON and Markdown
- `POST /api/jira/{project_key}` - submit generated stories to Jira

## Voice Input Mode

Voice input mode streams live microphone audio to the OpenAI Realtime API and lets
server-side VAD detect when the user has finished speaking.

Requirements:

- Install `sounddevice`: `pip install sounddevice`
- Use a working microphone configured for your OS

Run voice mode:

```bash
python src/realtime_assistant/main.py --voice
```

The assistant sends PCM16 mono audio at 24 kHz to the Realtime API. Text mode is
still the default:

```bash
python src/realtime_assistant/main.py
```

## Tool Chain

The realtime session registers these tools with the model:

- `capture_requirement(requirement: str, category: str)`
- `ask_clarifying_question(topic: str, question: str)`
- `summarize_requirements()`
- `generate_user_stories()`
- `export_user_stories(format: str)`
- `submit_stories_to_jira(project_key: str)`

When the model calls a tool, `main.py` receives the function-call event, dispatches it through `tools.py`, writes the function output back to the conversation, and asks the realtime model to continue. Captured requirements are stored in `SessionMemory`, then used by `llm.py` to produce structured `UserStory` objects.

## Jira Integration

The assistant can submit generated user stories to Jira as Story issues. Configure these environment variables in `.env`:

```bash
JIRA_BASE_URL=https://your-org.atlassian.net
JIRA_USER_EMAIL=you@example.com
JIRA_API_TOKEN=your_jira_api_token_here
JIRA_STORY_POINTS_FIELD=story_points
```

Create a Jira API token at https://id.atlassian.com/manage-profile/security/api-tokens and use it as `JIRA_API_TOKEN`. The `JIRA_STORY_POINTS_FIELD` value should match your Jira story points field key.

Example dialogue:

```text
User: Submit these stories to Jira project MYAPP.
Assistant: Submitted 4 stories to MYAPP: MYAPP-101, MYAPP-102, MYAPP-103, MYAPP-104.
```

The tool returns the created issue keys so the assistant can report exactly which Jira issues were created.

## Example Session Transcript

```text
Assistant: Hi, I’ll help turn this discovery call into implementation-ready user stories. What problem are you trying to solve?

User: We need a task manager for small teams. People should create tasks, organize them by project, and get reminders.

[Requirement Captured]
ID: REQ-4A12C9E0
Category: functional
Text: Users can create tasks for small-team work.

[Requirement Captured]
ID: REQ-19B2D33F
Category: functional
Text: Users can organize tasks by project.

[Requirement Captured]
ID: REQ-80BA912A
Category: functional
Text: Users receive reminders for upcoming task deadlines.

Assistant: What should collaboration look like for the first release?

User: Project owners can invite teammates by email. Keep it simple.

[Requirement Captured]
ID: REQ-1D88F20A
Category: functional
Text: Project owners can invite teammates to shared projects by email.

User: Generate stories.

[Generated User Stories]
US-001 Create Personal Tasks
US-002 Organize Tasks By Project
US-003 Receive Due Date Reminders
US-004 Share A Project With Collaborators
```

## Sample Output

The repository includes a pre-populated fictional task-manager output at `user_stories.md` and `user_stories.json`. A generated Markdown story looks like this:

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

## Project Structure

```text
realtime-ai-assistant/
├── README.md
├── .env.example
├── requirements.txt
├── pyproject.toml
├── user_stories.json
├── user_stories.md
└── src/
    └── realtime_assistant/
        ├── main.py
        ├── tools.py
        ├── jira_client.py
        ├── models.py
        ├── llm.py
        ├── memory.py
        ├── prompts.py
        ├── export.py
        └── logging.py
```

## Notes

- `generate_user_stories` uses Pydantic structured output via `client.beta.chat.completions.parse` when available, with a JSON-schema fallback for compatible OpenAI client versions.
- The realtime client is terminal text-first. It uses the Realtime API WebSocket event loop and tool-calling flow, so audio input/output can be added without changing the memory, tool, export, or structured-output layers.
- No API keys are hardcoded. All credentials are read from `.env`.
