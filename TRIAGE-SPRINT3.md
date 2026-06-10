# Post-MVP Issue Triage — realtime-ai-assistant

## Triage Date
2026-06-09

## Context

The original MVP roadmap (TRIAGE.md) is fully shipped at v0.14.1. The four new issues (#60–63) and two remaining P3 legacy issues (#6, #7) constitute the post-MVP backlog. This triage scores and sequences them.

---

## Scoring Summary

| #  | Title                                         | User Value (0–3) | Risk | Dependency | Priority |
|----|-----------------------------------------------|------------------|------|------------|----------|
| 62 | Configurable model settings                   | 2                | L    | none       | **P1**   |
| 60 | Jira dry-run, preview, partial failure        | 3                | M    | none       | **P1**   |
| 63 | Selective story regeneration & refinement     | 3                | M    | #62        | **P1**   |
| 61 | SSE dashboard updates                         | 2                | M    | none       | **P2**   |
| 6  | Slack/Teams notifications                     | 1                | L    | none       | **P3**   |
| 7  | Export to Confluence                          | 1                | M    | none       | **P3**   |

---

## P1 — Build Next

### #62 — Configurable model settings
**Necessity:** 2/3. Teams using GPT-4o for story generation pay ~10× more than necessary for a structured output call. `--story-model` + env var covers the most common ask immediately.

**Risk:** L. Purely additive — new CLI flag, env var lookup, thread through `generate_user_stories`. No schema changes. Existing defaults unchanged.

**Scope:**
- Add `STORY_GENERATION_MODEL` env var (default `gpt-4o`), read in `llm.py`
- Add `--story-model` CLI flag in `main.py`, pass through to `generate_user_stories` and the `generate_user_stories` tool handler
- Surface active model names in startup log and `/api/session`
- Update `.env.example` and README
- Tests: env override, CLI flag, session metadata field

**Verdict:** Smallest scope of the four. No dependencies. Unblocks #63 (refinement prompt needs a configurable model call). **Do first.**

---

### #60 — Jira submission preview, dry-run, and partial failure handling
**Necessity:** 3/3. A PM handing off to engineering on a real client engagement cannot afford to create 12 malformed Jira issues and then manually delete them. The current all-or-nothing batch with opaque error handling is the biggest professionalism gap before real client use.

**Risk:** M. Touches `jira_client.py` (new dry-run path), `tools.py` (per-story status tracking), and `dashboard.py` (preview table). No model changes needed.

**Scope:**
- `JiraClient.preview_issue(story) -> dict` — builds and returns the full payload without calling create
- `submit_stories_to_jira` upgraded to return per-story `{story_id, status: pending|created|failed|skipped, issue_key?, error?}`
- Track submitted issue keys on `DiscoverySession` so retry skips already-created stories
- Dashboard: `GET /api/jira/preview` endpoint returning payload list; basic preview table in HTML
- Tests: dry-run output shape, partial failure isolation, retry skip behavior, dashboard endpoint

**Verdict:** Highest user value of the batch. Independent of #62/#63. **Do second.**

---

### #63 — Selective story regeneration & refinement
**Necessity:** 3/3. After a session, 1–2 stories routinely need splitting or sharper acceptance criteria. Full regeneration risks clobbering approved stories. This is the most common post-session workflow gap reported in PM tooling.

**Risk:** M. Needs a new LLM prompt for single-story refinement, careful memory update logic (preserve IDs or record replacement history), and dashboard action buttons. Depends on #62 being done so the refinement model is configurable independently of the realtime model.

**Scope:**
- New `refine_user_story(story_id, feedback)` tool and prompt in `llm.py` / `prompts.py`
- New `regenerate_user_story(story_id)` tool — re-runs generation for a single story's source requirements
- Memory update: replace by ID, preserve order, optionally record replaced story in a `replaced_stories` list on `DiscoverySession`
- Dashboard: "Refine" button per story card → inline feedback textarea → POST `/api/stories/{id}/refine`
- Tests: single-story replacement, feedback prompt injection, ID preservation, dashboard endpoint

**Dependency:** #62 (needs configurable `--story-model` / `STORY_GENERATION_MODEL` for the refinement call). **Do third, after #62.**

---

## P2 — Should Do

### #61 — Realtime dashboard updates via SSE
**Necessity:** 2/3. The 3-second polling loop works, but it creates choppy UX during a live session (requirement captured → up to 3s before it appears). SSE would make it feel live.

**Risk:** M. FastAPI supports SSE via `StreamingResponse` and `asyncio.Queue` event buses. The main risk is the event-bus plumbing across the async boundary between the Realtime WebSocket loop and the dashboard server. A dropped stream needs a clean fallback-to-poll path.

**Scope:**
- In-process `asyncio.Queue`-based event bus in `memory.py` or a new `events.py`
- `GET /api/events` SSE endpoint streaming JSON event lines
- Emit events on: requirement captured, story added/updated, export completed, Jira submission status
- Client-side: `EventSource` listener; fall back to polling on `onerror`
- Tests: event payload shape, at least one full emit→receive path with TestClient

**Verdict:** Good UX improvement but not blocking any real workflow. **Do after P1s are clear.**

---

## P3 — Nice-to-Have (carry over from original backlog)

### #6 — Slack/Teams Notifications
Low complexity (webhook POST on story generation / export). No structural dependencies. Useful for teams where the BA runs the session alone and pings the team when ready. Defer until P1/P2 are shipped.

### #7 — Export to Confluence
Requires Confluence REST API integration (page create/update). Moderate risk due to Confluence API auth complexity (cloud vs. server tokens). Dependent on a real user requesting it — no current evidence of demand. Keep as P3.

---

## Recommended Build Order

### Sprint 3 (next)
1. **#62** Configurable model settings — ~1 day, clears the way for #63
2. **#60** Jira dry-run & partial failure — ~1–2 days, highest client-facing value
3. **#63** Selective story refinement — ~2 days, depends on #62

### Sprint 4
4. **#61** SSE dashboard updates — ~1–2 days
5. **#6** Slack/Teams notifications — ~0.5 days
6. **#7** Confluence export — ~1–2 days (only if user demand confirmed)

---

## Open Questions

1. **#62 model precedence:** If both `--story-model` CLI flag and `STORY_GENERATION_MODEL` env var are set, which wins? Recommend CLI > env > hardcoded default (standard precedence).

2. **#60 idempotency:** Should submitted Jira issue keys persist across process restarts (i.e., written to the session JSON on disk), or only for the lifetime of the current run? On-disk persistence is safer for real client use.

3. **#63 replacement history:** Should replaced stories be soft-deleted (kept in `replaced_stories` list) or hard-deleted? Soft-delete is safer for auditing — a PM may want to compare versions.

4. **#61 SSE vs. WebSocket:** The issue proposes SSE (simpler, one-way, HTTP/1.1 compatible). Given the dashboard already uses REST polling, SSE is the right choice. A full WebSocket adds complexity with no benefit for a read-only event stream.
