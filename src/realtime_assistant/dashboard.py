from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ValidationError

from realtime_assistant.memory import memory
from realtime_assistant.models import Priority, RequirementCategory
from realtime_assistant.tools import export_user_stories, submit_stories_to_jira

app = FastAPI(title="Discovery Assistant Dashboard")


def _requirements_payload() -> list[dict[str, Any]]:
    return [requirement.model_dump(mode="json") for requirement in memory.list_requirements()]


def _stories_payload() -> list[dict[str, Any]]:
    return [story.model_dump(mode="json") for story in memory.list_user_stories()]


class RequirementUpdateRequest(BaseModel):
    text: str | None = None
    category: RequirementCategory | None = None


class StoryUpdateRequest(BaseModel):
    title: str | None = None
    as_a: str | None = None
    i_want: str | None = None
    so_that: str | None = None
    acceptance_criteria: list[str] | None = None
    priority: Priority | None = None
    story_points: int | None = None


def _validation_error(exc: ValidationError) -> HTTPException:
    messages = "; ".join(str(error["msg"]) for error in exc.errors())
    return HTTPException(status_code=422, detail=messages or "Invalid edit payload.")


@app.get("/", response_class=HTMLResponse)
async def root() -> HTMLResponse:
    return HTMLResponse(DASHBOARD_HTML)


@app.get("/api/requirements")
async def get_requirements() -> list[dict[str, Any]]:
    return _requirements_payload()


@app.patch("/api/requirements/{requirement_id}")
async def patch_requirement(
    requirement_id: str,
    request: RequirementUpdateRequest,
) -> dict[str, Any]:
    try:
        updated = memory.update_requirement(
            requirement_id,
            text=request.text,
            category=request.category,
        )
    except ValidationError as exc:
        raise _validation_error(exc) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Requirement {requirement_id} not found.")
    return updated.model_dump(mode="json")


@app.delete("/api/requirements/{requirement_id}")
async def delete_requirement(requirement_id: str) -> dict[str, Any]:
    if not memory.remove_requirement(requirement_id):
        raise HTTPException(status_code=404, detail=f"Requirement {requirement_id} not found.")
    return {
        "ok": True,
        "requirement_id": requirement_id,
        "requirement_count": len(memory.list_requirements()),
    }


@app.get("/api/stories")
async def get_stories() -> list[dict[str, Any]]:
    return _stories_payload()


@app.patch("/api/stories/{story_id}")
async def patch_story(story_id: str, request: StoryUpdateRequest) -> dict[str, Any]:
    try:
        updated = memory.update_user_story(
            story_id,
            title=request.title,
            as_a=request.as_a,
            i_want=request.i_want,
            so_that=request.so_that,
            acceptance_criteria=request.acceptance_criteria,
            priority=request.priority,
            story_points=request.story_points,
        )
    except ValidationError as exc:
        raise _validation_error(exc) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail=f"User story {story_id} not found.")
    return updated.model_dump(mode="json")


@app.get("/api/session")
async def get_session() -> dict[str, Any]:
    session = memory.get_current_session()
    return {
        "requirement_count": len(memory.list_requirements()),
        "story_count": len(memory.list_user_stories()),
        "session_id": session.session_id,
        "started_at": session.started_at.isoformat(),
    }


@app.post("/api/export")
async def post_export() -> dict[str, Any]:
    return await export_user_stories("both")


@app.post("/api/jira/{project_key}")
async def post_jira(project_key: str) -> dict[str, Any]:
    return await submit_stories_to_jira(project_key)


DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Discovery Assistant</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #0f172a;
      --panel: #111c33;
      --card: #17223a;
      --border: #26344f;
      --text: #ffffff;
      --muted: #94a3b8;
      --blue: #2563eb;
      --orange: #f97316;
      --red: #dc2626;
      --gray: #64748b;
      --green: #22c55e;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    header {
      position: sticky;
      top: 0;
      z-index: 5;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 18px 24px;
      background: rgba(15, 23, 42, 0.96);
      border-bottom: 1px solid var(--border);
    }

    h1, h2, h3, p { margin: 0; }

    h1 {
      font-size: 24px;
      font-weight: 750;
    }

    .actions, .counts {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 10px;
    }

    .count, button, .badge, .points {
      border: 1px solid var(--border);
      border-radius: 8px;
    }

    .count {
      padding: 8px 10px;
      color: var(--muted);
      background: #111827;
      font-size: 14px;
    }

    .count strong { color: var(--text); }

    button {
      min-height: 36px;
      padding: 0 13px;
      color: var(--text);
      background: #1f2937;
      font-weight: 650;
      cursor: pointer;
    }

    button:hover { background: #273449; }
    button.danger:hover { background: #7f1d1d; border-color: var(--red); }

    main {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 18px;
      padding: 24px;
    }

    section {
      min-width: 0;
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 18px;
    }

    section h2 {
      margin-bottom: 14px;
      font-size: 18px;
      font-weight: 700;
    }

    .list {
      display: grid;
      gap: 12px;
    }

    .card {
      display: grid;
      gap: 10px;
      padding: 14px;
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 8px;
    }

    .card-top {
      display: flex;
      align-items: start;
      justify-content: space-between;
      gap: 10px;
    }

    .card-actions {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 8px;
      justify-content: flex-end;
    }

    .edit-form {
      display: grid;
      gap: 10px;
    }

    .form-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }

    label {
      display: grid;
      gap: 5px;
      color: var(--muted);
      font-size: 13px;
      font-weight: 650;
    }

    input, textarea, select {
      width: 100%;
      min-height: 36px;
      padding: 8px 10px;
      color: var(--text);
      background: #0f172a;
      border: 1px solid var(--border);
      border-radius: 8px;
      font: inherit;
    }

    textarea {
      min-height: 76px;
      resize: vertical;
      line-height: 1.4;
    }

    .req-text, .story-line {
      line-height: 1.45;
      color: #e5e7eb;
    }

    .source-list {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 6px;
    }

    .muted {
      color: var(--muted);
      font-size: 13px;
    }

    .badge, .points {
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 0 8px;
      font-size: 12px;
      font-weight: 750;
      white-space: nowrap;
    }

    .functional { background: rgba(37, 99, 235, 0.18); color: #93c5fd; border-color: var(--blue); }
    .non-functional { background: rgba(249, 115, 22, 0.18); color: #fdba74; border-color: var(--orange); }
    .constraint { background: rgba(220, 38, 38, 0.18); color: #fca5a5; border-color: var(--red); }
    .assumption { background: rgba(100, 116, 139, 0.2); color: #cbd5e1; border-color: var(--gray); }
    .priority { background: rgba(34, 197, 94, 0.15); color: #86efac; border-color: var(--green); }
    .points { background: #0f172a; color: #cbd5e1; }

    ul {
      margin: 0;
      padding-left: 18px;
      color: #dbeafe;
      line-height: 1.45;
    }

    .empty {
      padding: 18px;
      color: var(--muted);
      border: 1px dashed var(--border);
      border-radius: 8px;
      text-align: center;
    }

    #toast {
      position: fixed;
      right: 18px;
      bottom: 18px;
      max-width: min(440px, calc(100vw - 36px));
      padding: 12px 14px;
      color: var(--text);
      background: #020617;
      border: 1px solid var(--border);
      border-radius: 8px;
      box-shadow: 0 18px 42px rgba(0, 0, 0, 0.36);
      white-space: pre-line;
      opacity: 0;
      transform: translateY(8px);
      transition: opacity 160ms ease, transform 160ms ease;
      pointer-events: none;
    }

    #toast.show {
      opacity: 1;
      transform: translateY(0);
    }

    @media (max-width: 860px) {
      header { align-items: flex-start; flex-direction: column; }
      main { grid-template-columns: 1fr; padding: 16px; }
      .form-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>🎙 Discovery Assistant</h1>
      <p class="muted" id="session-meta">Loading session...</p>
    </div>
    <div class="actions">
      <div class="counts">
        <span class="count">Requirements <strong id="requirement-count">0</strong></span>
        <span class="count">Stories <strong id="story-count">0</strong></span>
      </div>
      <button type="button" id="export-button">Export</button>
      <button type="button" id="jira-button">Submit to Jira</button>
    </div>
  </header>

  <main>
    <section>
      <h2>Requirements</h2>
      <div class="list" id="requirements"></div>
    </section>
    <section>
      <h2>User Stories</h2>
      <div class="list" id="stories"></div>
    </section>
  </main>

  <div id="toast"></div>

  <script>
    const requirementList = document.querySelector("#requirements");
    const storyList = document.querySelector("#stories");
    const requirementCount = document.querySelector("#requirement-count");
    const storyCount = document.querySelector("#story-count");
    const sessionMeta = document.querySelector("#session-meta");
    const toast = document.querySelector("#toast");
    const requirementCategories = ["functional", "non-functional", "constraint", "assumption"];
    const storyPriorities = ["must-have", "should-have", "could-have", "wont-have"];
    const storyPointOptions = [1, 2, 3, 5, 8, 13];
    let activeEdit = null;

    const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;"
    })[char]);

    const formatDate = (value) => value ? new Date(value).toLocaleString() : "";
    const selectOptions = (values, selected) => values.map((value) => `
      <option value="${escapeHtml(value)}"${value === selected ? " selected" : ""}>${escapeHtml(value)}</option>
    `).join("");

    function showToast(message) {
      toast.textContent = message;
      toast.classList.add("show");
      window.clearTimeout(showToast.timeout);
      showToast.timeout = window.setTimeout(() => toast.classList.remove("show"), 4200);
    }

    async function apiJson(url, options = {}) {
      const response = await fetch(url, {
        headers: { "Content-Type": "application/json", ...(options.headers || {}) },
        ...options
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = Array.isArray(payload.detail)
          ? payload.detail.map((item) => item.msg || JSON.stringify(item)).join("\\n")
          : payload.detail;
        throw new Error(detail || `Request failed with status ${response.status}`);
      }
      return payload;
    }

    function renderRequirementEdit(requirement) {
      return `
        <article class="card" data-requirement-id="${escapeHtml(requirement.id)}">
          <div class="edit-form">
            <label>
              Text
              <textarea data-field="text">${escapeHtml(requirement.text)}</textarea>
            </label>
            <label>
              Category
              <select data-field="category">${selectOptions(requirementCategories, requirement.category)}</select>
            </label>
            <div class="card-actions">
              <button type="button" data-action="save-requirement">Save</button>
              <button type="button" data-action="cancel-edit">Cancel</button>
            </div>
          </div>
          <p class="muted">${escapeHtml(requirement.id)} · ${escapeHtml(formatDate(requirement.captured_at))}</p>
        </article>
      `;
    }

    function renderRequirements(requirements) {
      requirementCount.textContent = requirements.length;
      if (!requirements.length) {
        requirementList.innerHTML = '<div class="empty">No requirements captured yet.</div>';
        return;
      }
      requirementList.innerHTML = requirements.map((requirement) => {
        if (activeEdit?.type === "requirement" && activeEdit.id === requirement.id) {
          return renderRequirementEdit(requirement);
        }
        return `
        <article class="card">
          <div class="card-top">
            <p class="req-text">${escapeHtml(requirement.text)}</p>
            <span class="badge ${escapeHtml(requirement.category)}">${escapeHtml(requirement.category)}</span>
          </div>
          <div class="card-actions">
            <button type="button" data-action="edit-requirement" data-id="${escapeHtml(requirement.id)}">Edit</button>
            <button type="button" class="danger" data-action="delete-requirement" data-id="${escapeHtml(requirement.id)}">Delete</button>
          </div>
          <p class="muted">${escapeHtml(requirement.id)} · ${escapeHtml(formatDate(requirement.captured_at))}</p>
        </article>
      `;
      }).join("");
    }

    function renderStoryEdit(story) {
      return `
        <article class="card" data-story-id="${escapeHtml(story.id)}">
          <div class="edit-form">
            <label>
              Title
              <input data-field="title" value="${escapeHtml(story.title)}">
            </label>
            <div class="form-grid">
              <label>
                As a
                <input data-field="as_a" value="${escapeHtml(story.as_a)}">
              </label>
              <label>
                I want
                <input data-field="i_want" value="${escapeHtml(story.i_want)}">
              </label>
            </div>
            <label>
              So that
              <textarea data-field="so_that">${escapeHtml(story.so_that)}</textarea>
            </label>
            <label>
              Acceptance Criteria
              <textarea data-field="acceptance_criteria">${escapeHtml((story.acceptance_criteria || []).join("\\n"))}</textarea>
            </label>
            <div class="form-grid">
              <label>
                Priority
                <select data-field="priority">${selectOptions(storyPriorities, story.priority)}</select>
              </label>
              <label>
                Story Points
                <select data-field="story_points">${selectOptions(storyPointOptions, story.story_points)}</select>
              </label>
            </div>
            <div class="card-actions">
              <button type="button" data-action="save-story">Save</button>
              <button type="button" data-action="cancel-edit">Cancel</button>
            </div>
          </div>
          <div class="source-list">
            <span class="muted">Source</span>
            ${(story.source_requirement_ids || []).map((id) => `<span class="badge">${escapeHtml(id)}</span>`).join("") || '<span class="muted">None</span>'}
          </div>
        </article>
      `;
    }

    function renderStories(stories) {
      storyCount.textContent = stories.length;
      if (!stories.length) {
        storyList.innerHTML = '<div class="empty">No user stories generated yet.</div>';
        return;
      }
      storyList.innerHTML = stories.map((story) => {
        if (activeEdit?.type === "story" && activeEdit.id === story.id) {
          return renderStoryEdit(story);
        }
        return `
        <article class="card">
          <div class="card-top">
            <h3>${escapeHtml(story.id)}: ${escapeHtml(story.title)}</h3>
            <span class="points">${escapeHtml(story.story_points)} pts</span>
          </div>
          <div class="story-line">
            <p><strong>As a</strong> ${escapeHtml(story.as_a)}</p>
            <p><strong>I want</strong> ${escapeHtml(story.i_want)}</p>
            <p><strong>So that</strong> ${escapeHtml(story.so_that)}</p>
          </div>
          <div class="source-list">
            <span class="muted">Source</span>
            ${(story.source_requirement_ids || []).map((id) => `<span class="badge">${escapeHtml(id)}</span>`).join("") || '<span class="muted">None</span>'}
          </div>
          <ul>${(story.acceptance_criteria || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
          <span class="badge priority">${escapeHtml(story.priority)}</span>
          <div class="card-actions">
            <button type="button" data-action="edit-story" data-id="${escapeHtml(story.id)}">Edit</button>
          </div>
        </article>
      `;
      }).join("");
    }

    async function refreshDashboard() {
      if (activeEdit) return;
      const [requirementsResponse, storiesResponse, sessionResponse] = await Promise.all([
        fetch("/api/requirements"),
        fetch("/api/stories"),
        fetch("/api/session")
      ]);
      const [requirements, stories, session] = await Promise.all([
        requirementsResponse.json(),
        storiesResponse.json(),
        sessionResponse.json()
      ]);
      renderRequirements(requirements);
      renderStories(stories);
      sessionMeta.textContent = `${session.session_id} · Started ${formatDate(session.started_at)}`;
    }

    requirementList.addEventListener("click", async (event) => {
      const button = event.target.closest("button");
      if (!button) return;
      const action = button.dataset.action;
      const id = button.dataset.id || button.closest("[data-requirement-id]")?.dataset.requirementId;
      try {
        if (action === "edit-requirement") {
          activeEdit = { type: "requirement", id };
          const requirements = await apiJson("/api/requirements");
          renderRequirements(requirements);
        } else if (action === "cancel-edit") {
          activeEdit = null;
          await refreshDashboard();
        } else if (action === "delete-requirement") {
          if (!window.confirm(`Delete ${id}?`)) return;
          await apiJson(`/api/requirements/${encodeURIComponent(id)}`, { method: "DELETE" });
          activeEdit = null;
          await refreshDashboard();
          showToast(`Deleted ${id}.`);
        } else if (action === "save-requirement") {
          const card = button.closest("[data-requirement-id]");
          await apiJson(`/api/requirements/${encodeURIComponent(id)}`, {
            method: "PATCH",
            body: JSON.stringify({
              text: card.querySelector('[data-field="text"]').value,
              category: card.querySelector('[data-field="category"]').value
            })
          });
          activeEdit = null;
          await refreshDashboard();
          showToast(`Saved ${id}.`);
        }
      } catch (error) {
        showToast(error.message);
      }
    });

    storyList.addEventListener("click", async (event) => {
      const button = event.target.closest("button");
      if (!button) return;
      const action = button.dataset.action;
      const id = button.dataset.id || button.closest("[data-story-id]")?.dataset.storyId;
      try {
        if (action === "edit-story") {
          activeEdit = { type: "story", id };
          const stories = await apiJson("/api/stories");
          renderStories(stories);
        } else if (action === "cancel-edit") {
          activeEdit = null;
          await refreshDashboard();
        } else if (action === "save-story") {
          const card = button.closest("[data-story-id]");
          const acceptanceCriteria = card.querySelector('[data-field="acceptance_criteria"]').value
            .split("\\n")
            .map((item) => item.trim())
            .filter(Boolean);
          await apiJson(`/api/stories/${encodeURIComponent(id)}`, {
            method: "PATCH",
            body: JSON.stringify({
              title: card.querySelector('[data-field="title"]').value,
              as_a: card.querySelector('[data-field="as_a"]').value,
              i_want: card.querySelector('[data-field="i_want"]').value,
              so_that: card.querySelector('[data-field="so_that"]').value,
              acceptance_criteria: acceptanceCriteria,
              priority: card.querySelector('[data-field="priority"]').value,
              story_points: Number(card.querySelector('[data-field="story_points"]').value)
            })
          });
          activeEdit = null;
          await refreshDashboard();
          showToast(`Saved ${id}.`);
        }
      } catch (error) {
        showToast(error.message);
      }
    });

    document.querySelector("#export-button").addEventListener("click", async () => {
      const response = await fetch("/api/export", { method: "POST" });
      const result = await response.json();
      const paths = (result.paths || []).join("\\n");
      showToast(result.ok ? `Exported ${result.story_count} stories\\n${paths}` : `Export failed: ${result.error || "unknown error"}`);
    });

    document.querySelector("#jira-button").addEventListener("click", async () => {
      const key = window.prompt("Jira project key");
      if (!key) return;
      const response = await fetch(`/api/jira/${encodeURIComponent(key)}`, { method: "POST" });
      const result = await response.json();
      const issueKeys = (result.created_issues || []).map((issue) => issue.key || issue).join(", ");
      showToast(result.ok ? `Submitted ${result.count} issues: ${issueKeys}` : `Jira failed: ${result.error || "unknown error"}`);
    });

    refreshDashboard().catch((error) => showToast(`Refresh failed: ${error.message}`));
    setInterval(() => refreshDashboard().catch((error) => showToast(`Refresh failed: ${error.message}`)), 3000);
  </script>
</body>
</html>
"""
