"""Confluence Cloud REST API client (stdlib urllib, no third-party deps)."""

from __future__ import annotations

import base64
import html
import json
from urllib import error, parse, request

from realtime_assistant.models import (
    ConfluenceConfig,
    Requirement,
    SessionSummary,
    UserStory,
)


class ConfluenceClient:
    def __init__(self, config: ConfluenceConfig) -> None:
        self.config = config
        self.base_url = config.base_url.rstrip("/")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def export_discovery_page(
        self,
        title: str,
        requirements: list[Requirement],
        stories: list[UserStory],
        summary: SessionSummary | None = None,
        jira_issue_keys: list[str] | None = None,
        parent_page_id: str | None = None,
    ) -> str:
        """Create or update a Confluence page and return its URL.

        If a page with *title* already exists in the configured space it is
        updated in-place; otherwise a new page is created.  Returns the full
        browser URL to the resulting page.
        """
        body = _build_page_body(requirements, stories, summary, jira_issue_keys, self.base_url)
        existing_id = self._find_page(title)
        if existing_id:
            self._update_page(existing_id, title, body)
            return self._page_url(existing_id)
        page_id = self._create_page(title, body, parent_page_id)
        return self._page_url(page_id)

    def validate_space(self, space_key: str) -> bool:
        """Return True if the space exists and is accessible."""
        try:
            self._request("GET", f"/wiki/rest/api/space/{space_key}")
        except RuntimeError:
            return False
        return True

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _find_page(self, title: str) -> str | None:
        """Return the page ID if a page with this title exists in the space, else None."""
        params = f"spaceKey={self.config.space_key}&title={parse.quote(title)}&expand=version"
        data = self._request("GET", f"/wiki/rest/api/content?{params}")
        results = data.get("results", [])
        if results:
            return str(results[0]["id"])
        return None

    def _create_page(self, title: str, body: str, parent_page_id: str | None) -> str:
        payload: dict = {
            "type": "page",
            "title": title,
            "space": {"key": self.config.space_key},
            "body": {"storage": {"value": body, "representation": "storage"}},
        }
        if parent_page_id:
            payload["ancestors"] = [{"id": parent_page_id}]
        response = self._request("POST", "/wiki/rest/api/content", payload)
        page_id = response.get("id")
        if not isinstance(page_id, str) or not page_id:
            raise RuntimeError("Confluence page creation response did not include a page ID.")
        return page_id

    def _update_page(self, page_id: str, title: str, body: str) -> None:
        # Fetch current version number first
        existing = self._request("GET", f"/wiki/rest/api/content/{page_id}?expand=version")
        current_version = existing["version"]["number"]
        payload = {
            "type": "page",
            "title": title,
            "version": {"number": current_version + 1},
            "body": {"storage": {"value": body, "representation": "storage"}},
        }
        self._request("PUT", f"/wiki/rest/api/content/{page_id}", payload)

    def _page_url(self, page_id: str) -> str:
        return f"{self.base_url}/wiki/spaces/{self.config.space_key}/pages/{page_id}"

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.base_url}{path}",
            data=body,
            method=method,
            headers={
                "Accept": "application/json",
                "Authorization": self._authorization_header(),
                "Content-Type": "application/json",
            },
        )
        try:
            with request.urlopen(req) as resp:
                status = resp.getcode()
                content = resp.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Confluence API request failed with status {exc.code}: {detail}"
            ) from exc
        except error.URLError as exc:
            raise RuntimeError(f"Confluence API request failed: {exc.reason}") from exc

        if status < 200 or status >= 300:
            raise RuntimeError(f"Confluence API request failed with status {status}: {content}")
        if not content:
            return {}
        return json.loads(content)

    def _authorization_header(self) -> str:
        raw = f"{self.config.user_email}:{self.config.api_token}".encode()
        return f"Basic {base64.b64encode(raw).decode('ascii')}"


# ---------------------------------------------------------------------------
# Page body builder (Confluence storage format)
# ---------------------------------------------------------------------------

def _esc(text: str) -> str:
    return html.escape(str(text), quote=True)


def _build_page_body(
    requirements: list[Requirement],
    stories: list[UserStory],
    summary: SessionSummary | None,
    jira_issue_keys: list[str] | None,
    base_url: str,
) -> str:
    parts: list[str] = []

    # Executive summary section
    if summary:
        parts.append(f"<h2>Executive Summary</h2><p>{_esc(summary.overview)}</p>")
        if summary.open_questions:
            qs = "".join(f"<li>{_esc(q)}</li>" for q in summary.open_questions)
            parts.append(f"<h3>Open Questions</h3><ul>{qs}</ul>")
        if summary.risks_and_assumptions:
            rs = "".join(f"<li>{_esc(r)}</li>" for r in summary.risks_and_assumptions)
            parts.append(f"<h3>Risks &amp; Assumptions</h3><ul>{rs}</ul>")

    # Requirements table
    parts.append("<h2>Captured Requirements</h2>")
    if requirements:
        rows = "".join(
            f"<tr><td>{_esc(r.id)}</td><td>{_esc(r.category)}</td>"
            f"<td>{_esc(r.confidence)}</td><td>{_esc(r.text)}</td></tr>"
            for r in requirements
        )
        parts.append(
            "<table><tbody>"
            "<tr><th>ID</th><th>Category</th><th>Confidence</th><th>Requirement</th></tr>"
            f"{rows}</tbody></table>"
        )
    else:
        parts.append("<p><em>No requirements captured.</em></p>")

    # User stories
    parts.append("<h2>User Stories</h2>")
    jira_keys = list(jira_issue_keys or [])
    for i, story in enumerate(stories):
        jira_key = jira_keys[i] if i < len(jira_keys) else None
        jira_link = (
            f' &mdash; <a href="{_esc(base_url)}/browse/{_esc(jira_key)}">{_esc(jira_key)}</a>'
            if jira_key
            else ""
        )
        source = _esc(", ".join(story.source_requirement_ids) or "None")
        criteria = "".join(f"<li>{_esc(c)}</li>" for c in story.acceptance_criteria)
        parts.append(
            f"<h3>{_esc(story.id)}: {_esc(story.title)}{jira_link}</h3>"
            f"<p><strong>Priority:</strong> {_esc(story.priority)} &nbsp; "
            f"<strong>Points:</strong> {_esc(str(story.story_points))}</p>"
            f"<p><strong>As a</strong> {_esc(story.as_a)}, "
            f"<strong>I want</strong> {_esc(story.i_want)}, "
            f"<strong>so that</strong> {_esc(story.so_that)}.</p>"
            f"<p><strong>Source Requirements:</strong> {source}</p>"
            f"<ul>{criteria}</ul>"
        )

    if not stories:
        parts.append("<p><em>No user stories generated yet.</em></p>")

    return "\n".join(parts)
