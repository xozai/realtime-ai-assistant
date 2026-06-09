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
| Voice output playback (`SpeakerStream`, PCM16) | ✅ Shipped |
| Web dashboard (FastAPI, dark theme, live refresh, inline editing) | ✅ Shipped |
| Executive summary (`generate_session_summary`) | ✅ Shipped |
| Conversation transcript (JSON + Markdown) | ✅ Shipped |
| Session persist and resume (`--resume`) | ✅ Shipped |
| WebSocket reconnection with bounded backoff | ✅ Shipped |
| Story traceability to source requirements | ✅ Shipped |
| Requirement coverage and gap analysis | ✅ Shipped |
| Session-aware export destinations | ✅ Shipped |
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
OPENAI_API_KEY=***
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
pip install sounddevice   # one-time; requires a working microphone and speaker
python src/realtime_assistant/main.py --voice
```

Streams PCM16 mono audio at 24 kHz to the Realtime API. Server-side VAD detects end of speech. Assistant audio responses are played back in real time via `SpeakerStream`.

### Scripted session

```bash
python src/realtime_assistant/main.py --prompts "We need a task manager|Users need tasks and reminders|Generate stories"
```

### Resume a previous session

```bash
python src/realtime_assistant/main.py --resume DISC-001
```

Loads `sessions/DISC-001.json` before connecting — requirements, stories, and summary from the prior session are restored and replayed as context.

---

## CLI Flags

| Flag | Default | Description |
|---|---|---|
| `--voice` | off | Live microphone input + speaker output (requires `sounddevice`) |
| `--no-dashboard` | off | Disable the web dashboard |
| `--dashboard-port PORT` | `8000` | Dashboard port |
| `--resume SESSION_ID` | unset | Load `sessions/SESSION_ID.json` before connecting |
| `--session-id SESSION_ID` | generated | Start a new session with a known ID |
| `--output-dir PATH` | `exports/` | Directory for generated JSON and Markdown exports |
| `--export-name NAME` | `user_stories` | Base filename for generated exports, without extension |
| `--reconnect-attempts N` | `3` | Times to retry a dropped WebSocket before giving up |
| `--reconnect-delay SECS` | `1.0` | Initial backoff delay; doubles each attempt |
| `--reconnect-max-delay SECS` | `8.0` | Backoff ceiling in seconds |
| `--no-transcript` | off | Disable writing conversation transcript files |

---

## Web Dashboard

The FastAPI dashboard runs in the same process and shows live requirements, user stories, coverage analysis, and executive summary with a dark-theme layout. Auto-refreshes every 3 seconds.

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
| `PATCH` | `/api/requirements/{requirement_id}` | Update requirement text/category |
| `DELETE` | `/api/requirements/{requirement_id}` | Delete one requirement |
| `GET` | `/api/stories` | All generated user stories |
| `PATCH` | `/api/stories/{story_id}` | Update story fields, acceptance criteria, priority, points |
| `GET` | `/api/summary` | Current executive summary (`null` if not yet generated) |
| `POST` | `/api/summary/generate` | Generate and store executive summary via LLM |
| `GET` | `/api/coverage` | Requirement coverage report (coverage %, uncovered list) |
| `GET` | `/api/session` | Session ID, start time, counts |
| `POST` | `/api/export` | Export stories to JSON + Markdown |
| `POST` | `/api/jira/{project_key}` | Submit stories to Jira |

The dashboard has **Edit**, **Delete**, **Export**, **Coverage**, and **Submit to Jira** controls that call these endpoints directly from the browser.

---

## Tool Chain

The Realtime session registers these tools with the model:

| Tool | Description |
|---|---|
| `capture_requirement(requirement, category)` | Store a requirement in session memory |
| `ask_clarifying_question(topic, question)` | Log a clarifying question |
| `summarize_requirements()` | Print all captured requirements to terminal |
| `generate_user_stories()` | Produce structured `UserStory` objects via Chat Completions |
| `generate_session_summary()` | Generate a structured executive summary (overview, key requirements, open questions, risks) |
| `analyze_story_coverage()` | Compute per-requirement coverage from story `source_requirement_ids`; flags uncovered gaps |
| `export_user_stories(format, output_dir, export_name)` | Write JSON and Markdown exports; destination fields are optional |
| `submit_stories_to_jira(project_key)` | Create Jira Story issues for each story; warns if uncovered must-have requirements exist |

**Requirement categories:** `functional` · `non-functional` · `constraint` · `assumption`

**Story priorities:** `must-have` · `should-have` · `could-have` · `wont-have`

**Story points:** Fibonacci — `1, 2, 3, 5, 8, 13` (Pydantic-validated)

---

## Requirement Coverage Analysis

After generating stories, call `analyze_story_coverage` to see which requirements are covered:

```text
Assistant: Coverage: 75% (3/4 requirements covered)

Uncovered:
  REQ-1D88F20A [functional]: Project owners can invite teammates by email.
```

The coverage report is included in JSON and Markdown exports, shown in the dashboard at `/api/coverage`, and checked before Jira submission — uncovered `must-have` requirements print a Rich warning but do not block the push.

Stories gain a `source_requirement_ids` field linking each story back to the requirements it addresses.

---

## WebSocket Reconnection

If the Realtime WebSocket drops mid-call, the assistant reconnects automatically with bounded exponential backoff, replays `session.update` to restore tools and prompts, and injects captured requirements and stories back into context so the conversation continues without loss.

```text
[yellow] Realtime connection dropped. Reconnecting (1/3) in 1.0s...
[green]  Realtime connection restored.
[cyan]   Replayed captured discovery context after reconnect.
```

Configure via `--reconnect-attempts`, `--reconnect-delay`, and `--reconnect-max-delay`.

---

## Conversation Transcripts

Every session writes a transcript to `transcripts/<session_id>/`:

- `transcript.md` — human-readable Markdown with speaker labels
- `transcript.json` — machine-readable JSON with timestamps and metadata

Pass `--no-transcript` to disable.

---

## Session Persistence and Resume

Sessions are saved to `sessions/<session_id>.json` as requirements, stories, and summary accumulate. Resume a prior session with:

```bash
python src/realtime_assistant/main.py --resume DISC-001
```

Context is replayed as a `conversation.item.create` message so the assistant picks up exactly where the previous call left off.

---

## Voice Input + Output Mode

```bash
pip install sounddevice
python src/realtime_assistant/main.py --voice
```

- **Input:** `MicrophoneStream` streams PCM16 mono at 24 kHz; server-side VAD handles turn detection
- **Output:** `SpeakerStream` plays assistant audio responses in real time via `sounddevice.RawOutputStream`
- Session config switches to `modalities: ["text", "audio"]`
- Text mode remains the default — `sounddevice` is only imported when `--voice` is active

---

## Jira Integration

Submits generated stories to Jira as Story issues via the Atlassian REST API v3. Uses stdlib `urllib` — no extra dependencies.

Add to `.env`:

```bash
JIRA_BASE_URL=https://your-org.atlassian.net
JIRA_USER_EMAIL=you@example.com
JIRA_API_TOKEN=your_a...here
JIRA_STORY_POINTS_FIELD=story_points   # or customfield_10016
```

### Priority mapping

| Story priority | Jira priority |
|---|---|
| `must-have` | Highest |
| `should-have` | High |
| `could-have` | Medium |
| `wont-have` | Low |

Before submitting, the tool warns (Rich console) if any uncovered `must-have` requirements exist.

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

[Requirement Captured] REQ-1D88F20A · functional
  Project owners can invite teammates to shared projects by email.

User: Generate stories.

[Generated User Stories]
US-001  Create Personal Tasks              must-have    3 pts   sources: REQ-4A12C9E0
US-002  Organize Tasks By Project          should-have  5 pts   sources: REQ-19B2D33F
US-003  Receive Due Date Reminders         must-have    5 pts   sources: REQ-80BA912A
US-004  Share A Project With Collaborators could-have   8 pts   sources: REQ-1D88F20A

User: Analyze coverage.

Coverage: 100% (4/4 requirements covered)
```

---

## Sample Output

Pre-populated fictional sample output lives at `user_stories.md` and `user_stories.json`.
Generated exports are written to `exports/<session_id>/user_stories.json` and
`exports/<session_id>/user_stories.md` by default. Use `--output-dir PATH` and
`--export-name NAME` to customize.

```bash
python src/realtime_assistant/main.py --session-id DISC-001 --output-dir ./artifacts --export-name backlog
# writes artifacts/DISC-001/backlog.json and artifacts/DISC-001/backlog.md
```

---

## Project Structure

```text
realtime-ai-assistant/
├── README.md
├── CHANGELOG.md
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
│       ├── main.py              # async entry point, WebSocket loop, reconnection, CLI flags
│       ├── tools.py             # tool definitions, handlers, dispatch map
│       ├── models.py            # Pydantic models (Requirement, UserStory, CoverageReport...)
│       ├── llm.py               # structured output + story generation
│       ├── memory.py            # SessionMemory CRUD + session persistence
│       ├── prompts.py           # SYSTEM_PROMPT, VOICE_MODE_INTRO, story prompt
│       ├── export.py            # JSON + Markdown export (includes coverage report)
│       ├── coverage.py          # CoverageReport, analyze_coverage()
│       ├── transcript.py        # TranscriptWriter (JSON + Markdown)
│       ├── jira_client.py       # JiraClient (stdlib urllib, no extra deps)
│       ├── audio.py             # MicrophoneStream + SpeakerStream for --voice mode
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
    ├── test_speaker_stream.py
    ├── test_realtime_reconnect.py
    ├── test_transcript.py
    ├── test_session_persistence.py
    ├── test_summary.py
    ├── test_llm.py
    └── test_dashboard.py
```

---

## Tests

```bash
pip install pytest pytest-asyncio fastapi httpx uvicorn
pytest tests/ -v
```

| Test file | What it covers |
|---|---|
| `test_models.py` | Pydantic validation, Fibonacci points, category/priority literals, coverage models |
| `test_memory.py` | SessionMemory CRUD, duplicate ID handling, session persistence |
| `test_export.py` | JSON + Markdown export, coverage report inclusion, overwrite behavior |
| `test_tools.py` | Tool handler functions (mocked OpenAI) |
| `test_prompts.py` | SYSTEM_PROMPT content assertions |
| `test_jira_client.py` | JiraClient HTTP (mocked), priority mapping, description format |
| `test_tool_jira.py` | `submit_stories_to_jira` handler (mocked), error cases, coverage warning |
| `test_audio.py` | `MicrophoneStream` (sounddevice fully mocked) |
| `test_speaker_stream.py` | `SpeakerStream` enqueue + PCM playback (sounddevice fully mocked) |
| `test_voice_mode.py` | Voice session config, `voice_sender` encoding, `--voice` wiring |
| `test_realtime_reconnect.py` | Reconnection loop, bounded backoff, context replay |
| `test_transcript.py` | Transcript write, speaker labels, session metadata |
| `test_session_persistence.py` | Session save/load/resume round-trip |
| `test_summary.py` | Executive summary generation and storage |
| `test_llm.py` | LLM structured output helpers |
| `test_dashboard.py` | FastAPI endpoints via TestClient, including `/api/coverage` |

**Current count: 127 passing, 0 failures.**

---

## Repo Docs

| File | Description |
|---|---|
| `CHANGELOG.md` | Auto-generated changelog (release-please) |
| `REVIEW.md` | Code review findings (critical / major / minor severity) |
| `TEST_RESULTS.md` | Test run summary — baseline failures found and fixed |
| `MVP_ROADMAP.md` | 10-feature roadmap with complexity, priority, implementation notes |

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
- WebSocket reconnection uses PKCE-safe bounded exponential backoff; context replay injects a `conversation.item.create` summary message rather than re-sending raw events.
- No credentials are hardcoded. All secrets are read from `.env` via `python-dotenv`.
