# MVP Issue Triage — realtime-ai-assistant

## Triage Date
2026-06-07

## MVP Definition

A PM or BA can run a real client discovery call using this assistant, capture all requirements reliably, generate implementation-ready Agile user stories with full traceability, and hand off to engineering via Jira — with enough robustness and audit trail that the output can be used in a professional engagement without manual cleanup or re-running the session.

---

## Scoring Summary

| # | Title | Necessity (0-3) | Risk | Dependency | Priority |
|---|-------|-----------------|------|------------|----------|
| 23 | WebSocket reconnection | 3 | M | none | **P1** |
| 1 | Conversation Transcript | 3 | L | none | **P1** |
| 19 | Link stories to source requirements | 3 | L | none | **P1** |
| 15 | Technical Debt: Memory API + Export | 3 | L | none | **P1** |
| 2 | Session Resume | 2 | M | #1 | **P2** |
| 17 | Dashboard editing (req + stories) | 2 | M | none | **P2** |
| 18 | Configurable export destinations | 2 | L | none | **P2** |
| 25 | Executive summary generation | 2 | L | none | **P2** |
| 20 | Requirement coverage + gap analysis | 2 | M | #19 | **P2** |
| 22 | Voice output playback | 2 | M | none | **P2** |
| 4 | Confidence Scoring | 1 | M | none | **P3** |
| 5 | Requirement Deduplication | 1 | M | none | **P3** |
| 24 | Session token & cost tracking | 1 | L | none | **P3** |
| 6 | Slack/Teams Notifications | 1 | L | none | **P3** |
| 7 | Export to Confluence | 1 | M | #7 Jira shipped | **P3** |
| 12 | Export to PDF | 0 | M | none | WONTFIX |
| 3 | Multi-Product Support | 1 | H | #2 | **P3** |
| 13 | Interactive Requirement Management | duplicate of #17 | — | — | CLOSED |
| 14 | Requirement Traceability | duplicate of #19 | — | — | CLOSED |
| 16 | Session Snapshotting & Auto-Recovery | duplicate of #2 | — | — | CLOSED |
| 21 | CI: run pytest and ruff | shipped in PR #26 | — | — | CLOSED |

---

## P1 — Must-Have Issues

| # | Title | Rationale | Dependency |
|---|-------|-----------|------------|
| [#23](https://github.com/xozai/realtime-ai-assistant/issues/23) | Realtime session reconnection on dropped WebSocket | A dropped connection during a live client call loses all in-memory state. The issue body identifies this as the highest-impact reliability gap. Without reconnection the tool cannot be trusted in a real engagement. | None |
| [#1](https://github.com/xozai/realtime-ai-assistant/issues/1) | Conversation Transcript — full session audit trail | Once the process exits, the conversation is gone. A PM/BA needs the verbatim record to defend why each requirement exists. Also enables session resume and traceability. | None |
| [#19](https://github.com/xozai/realtime-ai-assistant/issues/19) | Link generated stories back to source requirements | `UserStory` has no `source_requirement_ids`. Without it, engineers cannot audit why a story exists, and Jira issues lack traceability. The issue proposes adding the field, updating generation prompt, exports, and Jira descriptions. | None |
| [#15](https://github.com/xozai/realtime-ai-assistant/issues/15) | Technical Debt: Complete Memory API and Export Exposures | References REVIEW.md findings: incomplete memory API and unexposed export functions reduce testability and API clarity. These are prerequisite fixes that will block other features if left open. | None |

> **4 P1 issues** (≤5 constraint satisfied)

---

## P2 — Should-Have Issues

| # | Title | Rationale | Dependency |
|---|-------|-----------|------------|
| [#2](https://github.com/xozai/realtime-ai-assistant/issues/2) | Session Resume — persist and continue a discovery session | Real discovery spans multiple calls. Without resume, the tool is single-shot only. Pairs with Conversation Transcript (#1). | #1 (transcript provides session_id anchor) |
| [#17](https://github.com/xozai/realtime-ai-assistant/issues/17) | Dashboard editing for requirements and stories | Dashboard is currently read-only. Inline editing of requirements and stories before export/Jira is a natural next step. Well-specified: new API endpoints, Pydantic validation preserved. | None |
| [#18](https://github.com/xozai/realtime-ai-assistant/issues/18) | Configurable export destinations and filenames | Fixed root-level filenames overwrite sample files on every session. Session-specific export paths are needed for real multi-session use. Low risk, clear scope. | None |
| [#25](https://github.com/xozai/realtime-ai-assistant/issues/25) | Generate discovery-call executive summary | Stakeholder-facing narrative (problem, scope, key requirements, open questions, risks) as a Pydantic model. Adds direct PM hand-off value. Integrates with export and dashboard. | None |
| [#20](https://github.com/xozai/realtime-ai-assistant/issues/20) | Requirement coverage and gap analysis | Explicit quality gate before Jira submission. Identifies uncovered requirements, suggests clarifying questions. Composes with #19 traceability. | #19 |
| [#22](https://github.com/xozai/realtime-ai-assistant/issues/22) | Voice output playback — play assistant audio in --voice mode | `--voice` is currently half-duplex: user speaks, assistant replies only in text. `response.audio.delta` events are already received but not played. Fix is well-scoped: `SpeakerStream` in `audio.py`. | None |

---

## P3 — Nice-to-Have Issues

| # | Title | Rationale |
|---|-------|-----------|
| [#4](https://github.com/xozai/realtime-ai-assistant/issues/4) | Confidence Scoring — rate requirement clarity | Useful signal for PMs but adds an LLM call per requirement. Launch viable without it. |
| [#5](https://github.com/xozai/realtime-ai-assistant/issues/5) | Requirement Deduplication via embeddings | Reduces Jira noise but discovery conversations are relatively short; manual review covers this. Adds embedding API dependency. |
| [#3](https://github.com/xozai/realtime-ai-assistant/issues/3) | Multi-Product Support — isolated sessions per project | High implementation risk (replaces global memory singleton). Only relevant once multiple clients are active. Defer until Session Resume (#2) is proven. |
| [#6](https://github.com/xozai/realtime-ai-assistant/issues/6) | Slack/Teams Notifications | Nice-to-have ping, zero-crash if webhook missing. Easy to add post-MVP. |
| [#7](https://github.com/xozai/realtime-ai-assistant/issues/7) | Export to Confluence | Good complement to Jira. Not required for the core hand-off workflow. |
| [#24](https://github.com/xozai/realtime-ai-assistant/issues/24) | Session token & cost tracking | Operational visibility. Important eventually, not blocking MVP. |

---

## Closed / Duplicate Issues

| # | Title | Action | Reason |
|---|-------|--------|--------|
| #21 | CI: run pytest and ruff on pull requests | Closed — shipped | Delivered in PR #26: `.github/workflows/ci.yml` |
| #13 | Feature: Interactive Requirement Management | Closed — duplicate of #17 | #17 is more detailed: scoped API endpoints, Pydantic validation, dashboard controls, acceptance criteria |
| #14 | Feature: Requirement Traceability | Closed — duplicate of #19 | #19 is more detailed: `source_requirement_ids` field, prompt update, exports, Jira descriptions, tests |
| #16 | Feature: Session Snapshotting & Auto-Recovery | Closed — duplicate of #2 | #2 covers the same ground (DiscoverySession persistence, resume, auto-save on shutdown) with a complete implementation spec |
| #12 | Feature: Export to PDF | Closed — out of scope | PDF adds a binary rendering dependency (e.g. weasyprint/reportlab) with no clear stakeholder demand vs Markdown/Confluence. WONTFIX for MVP. |

---

## Recommended Build Order

### Sprint 1 — Reliability & Traceability Foundation
1. **#15** Technical Debt (Memory API + Export) — unblocks everything cleanly
2. **#23** WebSocket reconnection — removes the biggest reliability risk before any real client use
3. **#1** Conversation Transcript — audit trail; session_id foundation for resume and traceability
4. **#19** Link stories to source requirements — completes the requirement→story→Jira traceability chain

### Sprint 2 — Session Quality & Output Polish
5. **#18** Configurable export destinations — prevents overwriting sample files; low risk
6. **#17** Dashboard editing — makes the UI an active review surface, not a monitor
7. **#25** Executive summary — stakeholder-ready narrative output
8. **#2** Session Resume — multi-call discovery; builds on #1 transcript/session_id

### Sprint 3 — Voice + Coverage
9. **#22** Voice output playback — completes the voice mode duplex gap
10. **#20** Requirement coverage + gap analysis — quality gate before Jira submission; builds on #19

### Post-MVP
11. **#4** Confidence Scoring
12. **#5** Requirement Deduplication
13. **#24** Cost tracking
14. **#6** Slack/Teams Notifications
15. **#7** Export to Confluence
16. **#3** Multi-Product Support (after #2 is stable)

---

## Open Questions

1. **#15 scope**: REVIEW.md findings were partially addressed during initial development. Is #15 tracking specific remaining gaps, or can it be closed if a code audit shows they are resolved?

2. **#23 complexity**: The issue rates this as complexity L (large). Is there appetite to tackle it in Sprint 1 given the effort, or defer to Sprint 2 and accept the reliability risk for internal testing?

3. **#3 Multi-Product**: The global `memory` singleton replacement is a high-risk refactor. Should this wait until the user base is large enough to justify it, or is there a simpler `--project` flag approach that avoids the singleton replacement?

4. **#22 Voice output**: `sounddevice` is already an optional dep. Does the target deployment environment (macOS only, or cross-platform?) affect the speaker implementation choice?
