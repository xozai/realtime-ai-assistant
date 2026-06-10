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
| Confidence scoring on requirements | ✅ Shipped |
| Requirement deduplication via embeddings | ✅ Shipped |
| Session token and cost tracking | ✅ Shipped |
| Multi-product support (isolated sessions per project) | ✅ Shipped |

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

# Optional — story generation model (default gpt-4o)
STORY_GENERATION_MODEL=gpt-4o

# Optional — Jira integration
JIRA_BASE_URL=https://your-org.atlassian.net
JIRA_USER_EMAIL=you@example.com
JIRA_API_TOKEN=your_token_here
JIRA_STORY_POINTS_FIELD=story_points

# Optional — tune deduplication sensitivity (default 0.85)
DEDUP_THRESHOLD=0.85

# Optional — override API cost rates (per 1K tokens)
REALTIME_INPUT_PRICE_PER_1K=0.005
REALTIME_OUTPUT_PRICE_PER_1K=0.02
CHAT_INPUT_PRICE_PER_1K=0.0025
CHAT_OUTPUT_PRICE_PER_1K=0.01
EMBEDDING_PRICE_PER_1K=0.00002
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
python src/realtime_assistant/main.py --project acme --resume DISC-001
```

Loads `sessions/<project_key>/<session_id>.json` before connecting — requirements, stories, summary, and costs from the prior session are restored.

### Multi-product usage

```bash
# Start a new discovery session for a specific project
python src/realtime_assistant/main.py --project acme

# Resume an existing session under the same project
python src/realtime_assistant/main.py --project acme --resume DISC-042
```

Sessions, transcripts, and exports are isolated per project key. Switching `--project` starts a completely separate context with no bleed between projects.

---

## CLI Flags

| Flag | Default | Description |
|---|---|---|
| `--project PROJECT_KEY` | `default` | Discovery project key — isolates sessions, exports, transcripts |
| `--voice` | off | Live microphone input + speaker output (requires `sounddevice`) |
| `--model MODEL` | `gpt-4o-realtime-preview` | Realtime voice/text model |
| `--story-model MODEL` | `STORY_GENERATION_MODEL` or `gpt-4o` | Chat Completions model for story generation |
| `--no-dashboard` | off | Disable the web dashboard |
| `--dashboard-port PORT` | `8000` | Dashboard port |
| `--resume SESSION_ID` | unset | Load a prior session (scoped to `--project`) |
| `--session-id SESSION_ID` | generated | Start a new session with a known ID |
| `--output-dir PATH` | `exports/` | Directory for generated JSON and Markdown exports |
| `--export-name NAME` | `user_stories` | Base filename for generated exports, without extension |
| `--reconnect-attempts N` | `3` | Times to retry a dropped WebSocket before giving up |
| `--reconnect-delay SECS` | `1.0` | Initial backoff delay; doubles each attempt |
| `--reconnect-max-delay SECS` | `8.0` | Backoff ceiling in seconds |
| `--no-transcript` | off | Disable writing conversation transcript files |

---

## Web Dashboard

The FastAPI dashboard runs in the same process and shows live requirements (with confidence badges), user stories, coverage analysis, cost summary, and executive summary.

Open: **http://localhost:8000**

### Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Inline dark-theme SPA |
| `GET` | `/api/requirements` | All captured requirements (includes `confidence`) |
| `PATCH` | `/api/requirements/{requirement_id}` | Update requirement text/category |
| `DELETE` | `/api/requirements/{requirement_id}` | Delete one requirement |
| `GET` | `/api/stories` | All generated user stories |
| `PATCH` | `/api/stories/{story_id}` | Update story fields, acceptance criteria, priority, points |
| `GET` | `/api/summary` | Current executive summary (`null` if not yet generated) |
| `POST` | `/api/summary/generate` | Generate and store executive summary via LLM |
| `GET` | `/api/coverage` | Requirement coverage report (coverage %, uncovered list, low-confidence count) |
| `GET` | `/api/session` | Session ID, project key, start time, counts, token costs |
| `POST` | `/api/export` | Export stories to JSON + Markdown |
| `POST` | `/api/jira/{project_key}` | Submit stories to Jira; pass `?dry_run=true` to preview payloads without creating issues |

---

## Tool Chain

The Realtime session registers these tools with the model:

| Tool | Description |
|---|---|
| `capture_requirement(requirement, category)` | Store a requirement; auto-deduplicates via embeddings and scores confidence via LLM |
| `ask_clarifying_question(topic, question)` | Log a clarifying question |
| `summarize_requirements()` | Print requirements grouped by confidence; Rich-warns on low-confidence items |
| `generate_user_stories()` | Produce structured `UserStory` objects with `source_requirement_ids` via Chat Completions |
| `generate_session_summary()` | Generate a structured executive summary (overview, key requirements, open questions, risks) |
| `analyze_story_coverage()` | Compute per-requirement coverage from story source IDs; flags gaps; warns on low-confidence |
| `dedupe_requirements()` | On-demand pairwise similarity pass over stored requirements; reports near-duplicate pairs |
| `export_user_stories(format, output_dir, export_name)` | Write JSON and Markdown exports including coverage report |
| `submit_stories_to_jira(project_key, dry_run)` | Preview or create Jira Story issues; reports per-story success/failure/skipped results and warns if uncovered must-have requirements exist |

**Requirement categories:** `functional` · `non-functional` · `constraint` · `assumption`

**Requirement confidence:** `high` · `medium` · `low` — scored by LLM on capture; low items flagged for follow-up

**Story priorities:** `must-have` · `should-have` · `could-have` · `wont-have`

**Story points:** Fibonacci — `1, 2, 3, 5, 8, 13` (Pydantic-validated)

---

## Confidence Scoring

Every captured requirement is automatically scored by the LLM for how clearly it was articulated:

- **high** — well-defined, specific, testable
- **medium** — reasonable but could use clarification
- **low** — vague or ambiguous; the assistant is prompted to re-ask

Low-confidence items are highlighted in `summarize_requirements`, shown with a colored badge in the dashboard (green / yellow / red), included in exports, and surfaced in the coverage report's `low_confidence_count`.

---

## Requirement Deduplication

When a new requirement is captured, its embedding (`text-embedding-3-small`) is compared against all stored requirements. If cosine similarity exceeds the threshold (default `0.85`, env-configurable via `DEDUP_THRESHOLD`), the duplicate is silently merged rather than stored. A tool result explains the merge with the existing requirement ID.

Run `dedupe_requirements` at any time for an on-demand pairwise report of near-duplicate pairs still in the session.

---

## Token and Cost Tracking

Token usage is accumulated across the Realtime API and Chat Completions calls and stored on `DiscoverySession.costs`. At session end, a Rich table is printed:

```
┌─────────────────┬───────────────┬────────────────┬───────────────┐
│ Model           │ Input tokens  │ Output tokens  │ Est. cost USD │
├─────────────────┼───────────────┼────────────────┼───────────────┤
│ Realtime        │ 12,450        │ 3,820          │ $0.139        │
│ Chat completions│ 1,200         │ 680            │ $0.010        │
│ Embeddings      │ 340           │ —              │ $0.000        │
├─────────────────┼───────────────┼────────────────┼───────────────┤
│ Total           │               │                │ $0.149        │
└─────────────────┴───────────────┴────────────────┴───────────────┘
```

Cost rates are configurable via env vars (see Install section). The dashboard `GET /api/session` endpoint includes the full cost breakdown.

---

## Multi-Product Support

Use `--project PROJECT_KEY` to isolate sessions per product or client engagement:

```bash
# Two separate projects — no shared context
python src/realtime_assistant/main.py --project acme-crm
python src/realtime_assistant/main.py --project beta-payments
```

Sessions persist under `sessions/<project_key>/`, exports under `exports/<project_key>/`, and transcripts under `transcripts/<project_key>/`. Existing flat-path sessions (`sessions/<session_id>.json`) are still loaded as a backward-compatible fallback. The active project key is shown in the dashboard header and included in `GET /api/session`.

---

## Requirement Coverage Analysis

After generating stories, call `analyze_story_coverage`:

```text
Coverage: 75% (3/4 requirements covered)
Low-confidence requirements: 1

Uncovered:
  REQ-1D88F20A [functional]: Project owners can invite teammates by email.
```

The coverage report is included in JSON and Markdown exports, shown in the dashboard at `/api/coverage`, and checked before Jira submission — uncovered `must-have` requirements print a Rich warning but do not block the push.

---

## WebSocket Reconnection

If the Realtime WebSocket drops mid-call, the assistant reconnects automatically with bounded exponential backoff, replays `session.update`, and injects captured context back so the conversation continues without loss.

Configure via `--reconnect-attempts`, `--reconnect-delay`, and `--reconnect-max-delay`.

---

## Conversation Transcripts

Every session writes to `transcripts/<project_key>/<session_id>/`:

- `transcript.md` — human-readable Markdown with speaker labels
- `transcript.json` — machine-readable JSON with timestamps and metadata

Pass `--no-transcript` to disable.

---

## Session Persistence and Resume

Sessions are saved to `sessions/<project_key>/<session_id>.json`. Resume with:

```bash
python src/realtime_assistant/main.py --project acme --resume DISC-001
```

Context is replayed as a `conversation.item.create` message so the assistant picks up exactly where the previous call left off.

---

## Voice Input + Output Mode

```bash
pip install sounddevice
python src/realtime_assistant/main.py --voice
```

- **Input:** `MicrophoneStream` streams PCM16 mono at 24 kHz; server-side VAD handles turn detection
- **Output:** `SpeakerStream` plays assistant audio responses in real time
- Text mode remains the default — `sounddevice` is only imported when `--voice` is active

---

## Jira Integration

Submits generated stories to Jira as Story issues via the Atlassian REST API v3. Uses stdlib `urllib` — no extra dependencies.

Add to `.env` (see Install section). The `submit_stories_to_jira` tool requires an explicit Jira project key — it is intentionally separate from the discovery `--project` key.

Use `dry_run=true` to preview the exact Jira issue payloads before anything is created:

```text
submit_stories_to_jira(project_key="PROJ", dry_run=true)
POST /api/jira/PROJ?dry_run=true
```

Real submissions return a per-story `results` list with `success`, `failure`, or `skipped` status. A single failed story does not stop later stories from being attempted. Successful real submissions still include the legacy `created_issues` list and `count` for existing callers.

### Priority mapping

| Story priority | Jira priority |
|---|---|
| `must-have` | Highest |
| `should-have` | High |
| `could-have` | Medium |
| `wont-have` | Low |

---

## Example Session

```
Assistant: Hi! What problem are you solving today?

User: We need a task manager for small teams.

[Requirement Captured] REQ-4A12C9E0 · functional · confidence: high
  Users can create tasks for small-team work.

User: Teams should share tasks across projects.

[Requirement Captured] REQ-19B2D33F · functional · confidence: medium
  Users can organize tasks by project.

User: Remind users when tasks are nearly due.

[Requirement Captured] REQ-80BA912A · functional · confidence: high
  Users receive reminders for upcoming deadlines.

User: Generate stories.

[Generated User Stories]
US-001  Create Personal Tasks        must-have    3 pts   sources: REQ-4A12C9E0
US-002  Organize Tasks By Project    should-have  5 pts   sources: REQ-19B2D33F
US-003  Receive Due Date Reminders   must-have    5 pts   sources: REQ-80BA912A

User: Analyze coverage.

Coverage: 100% (3/3 requirements covered). Low-confidence: 1 (REQ-19B2D33F).

--- Session End ---
Realtime: 8,200 input / 2,100 output — $0.083
Chat:       980 input /   420 output — $0.007
Total: $0.090
```

---

## Project Structure

```text
realtime-ai-assistant/
├── README.md
├── CHANGELOG.md
├── REVIEW.md
├── TEST_RESULTS.md
├── MVP_ROADMAP.md
├── .env.example
├── pyproject.toml
├── src/
│   └── realtime_assistant/
│       ├── main.py          # async entry point, CLI flags (incl. --project), reconnection
│       ├── tools.py         # tool definitions, handlers, dispatch map
│       ├── models.py        # Pydantic models: Requirement (confidence), UserStory,
│       │                    #   TokenUsage, SessionCosts, CoverageReport, DiscoverySession
│       ├── llm.py           # story generation, confidence scoring, embeddings
│       ├── memory.py        # SessionMemory: CRUD, dedup, cost accumulation, persistence
│       ├── prompts.py       # SYSTEM_PROMPT (includes low-confidence re-ask guidance)
│       ├── export.py        # JSON + Markdown export (includes coverage + confidence)
│       ├── coverage.py      # CoverageReport, analyze_coverage()
│       ├── transcript.py    # TranscriptWriter (JSON + Markdown, project-scoped paths)
│       ├── jira_client.py   # JiraClient (stdlib urllib)
│       ├── audio.py         # MicrophoneStream + SpeakerStream
│       ├── dashboard.py     # FastAPI SPA (confidence badges, cost section, project header)
│       ├── server.py        # uvicorn async task wrapper
│       └── logging.py       # Rich logger config
└── tests/
    ├── test_models.py             # Pydantic validation, confidence, TokenUsage, costs
    ├── test_memory.py             # SessionMemory CRUD, dedup, cost accumulation
    ├── test_export.py             # Export formats, confidence + coverage in output
    ├── test_tools.py              # Tool handlers (mocked OpenAI + embeddings)
    ├── test_dedup.py              # Deduplication: duplicate pair skipped, distinct pair stored
    ├── test_coverage.py           # Coverage report, low_confidence_count
    ├── test_llm.py                # Story generation, confidence scoring, cost accumulation
    ├── test_prompts.py            # SYSTEM_PROMPT assertions
    ├── test_jira_client.py        # JiraClient HTTP (mocked)
    ├── test_tool_jira.py          # submit_stories_to_jira (mocked), coverage warning
    ├── test_audio.py              # MicrophoneStream (sounddevice mocked)
    ├── test_speaker_stream.py     # SpeakerStream enqueue + playback (mocked)
    ├── test_voice_mode.py         # Voice session config, --voice wiring
    ├── test_realtime_reconnect.py # Reconnection loop, backoff, context replay
    ├── test_transcript.py         # Transcript write, project-scoped paths
    ├── test_session_persistence.py # Save/load/resume, multi-project isolation
    ├── test_summary.py            # Executive summary generation
    └── test_dashboard.py          # All FastAPI endpoints via TestClient
```

---

## Tests

```bash
pip install pytest pytest-asyncio fastapi httpx uvicorn
pytest tests/ -v
```

| Test file | What it covers |
|---|---|
| `test_models.py` | Pydantic validation, confidence field, TokenUsage math, SessionCosts |
| `test_memory.py` | SessionMemory CRUD, dedup threshold, cost accumulation methods |
| `test_export.py` | JSON + Markdown export, confidence + coverage in output |
| `test_tools.py` | Tool handlers (mocked OpenAI, embeddings, confidence scorer) |
| `test_dedup.py` | Duplicate pair skipped; distinct pair stored; pairwise dedupe report |
| `test_coverage.py` | Coverage report generation, `low_confidence_count` field |
| `test_llm.py` | Story generation, confidence scoring, chat usage accumulation |
| `test_prompts.py` | SYSTEM_PROMPT content assertions |
| `test_jira_client.py` | JiraClient HTTP (mocked), priority mapping |
| `test_tool_jira.py` | `submit_stories_to_jira` handler, coverage warning, project key guard |
| `test_audio.py` | `MicrophoneStream` (sounddevice fully mocked) |
| `test_speaker_stream.py` | `SpeakerStream` enqueue + PCM playback (mocked) |
| `test_voice_mode.py` | Voice session config, `voice_sender` encoding, `--voice` wiring |
| `test_realtime_reconnect.py` | Reconnection loop, bounded backoff, context replay |
| `test_transcript.py` | Transcript write, speaker labels, project-scoped paths |
| `test_session_persistence.py` | Session save/load/resume, multi-project isolation, flat-path fallback |
| `test_summary.py` | Executive summary generation and storage |
| `test_dashboard.py` | All FastAPI endpoints via TestClient, cost + project fields |

**Current count: 153 passing, 0 failures.**

---

## Repo Docs

| File | Description |
|---|---|
| `CHANGELOG.md` | Auto-generated changelog (release-please) |
| `REVIEW.md` | Code review findings |
| `TEST_RESULTS.md` | Test run summary |
| `MVP_ROADMAP.md` | Original 10-feature roadmap — all items shipped |

---

## License

MIT — see [LICENSE](LICENSE) for the full text.

All dependencies (`openai`, `pydantic`, `fastapi`, `rich`, `websockets`, `uvicorn`, `httpx`, `sounddevice`, `python-dotenv`) use permissive licenses (MIT, Apache 2.0, BSD-3). No copyleft dependencies.

---

## Notes

- `capture_requirement` now calls `text-embedding-3-small` for dedup and `gpt-4o` for confidence scoring on every requirement capture. Both calls are mocked in tests and lazy in voice mode.
- `generate_user_stories` uses Pydantic structured output via `client.beta.chat.completions.parse` with a JSON-schema fallback for compatible OpenAI client versions.
- Jira submission uses stdlib `urllib` only — no `requests` or `httpx` required in the core app.
- Sessions persist under `sessions/<project_key>/`. Flat-path sessions from earlier versions are still loaded as a fallback.
- Cost rates default to public OpenAI pricing but are fully configurable via env vars — update them when rates change.
- No credentials are hardcoded. All secrets are read from `.env` via `python-dotenv`.
