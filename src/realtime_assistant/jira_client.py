from __future__ import annotations

import base64
import json
from urllib import error, request

from realtime_assistant.models import JiraConfig, UserStory

PRIORITY_MAP = {
    "must-have": "Highest",
    "should-have": "High",
    "could-have": "Medium",
    "wont-have": "Low",
}


class JiraClient:
    def __init__(self, config: JiraConfig) -> None:
        self.config = config
        self.base_url = config.base_url.rstrip("/")

    def create_issue(self, project_key: str, story: UserStory) -> str:
        payload = {
            "fields": {
                "project": {"key": project_key},
                "summary": story.title,
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": self._format_description(story)}],
                        }
                    ],
                },
                "issuetype": {"name": "Story"},
                "priority": {"name": PRIORITY_MAP[story.priority]},
                self.config.story_points_field: story.story_points,
            }
        }
        response = self._request("POST", "/rest/api/3/issue", payload)
        issue_key = response.get("key")
        if not isinstance(issue_key, str) or not issue_key:
            raise RuntimeError("Jira issue creation response did not include an issue key.")
        return issue_key

    def validate_project(self, project_key: str) -> bool:
        try:
            self._request("GET", f"/rest/api/3/project/{project_key}")
        except RuntimeError:
            return False
        return True

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
            with request.urlopen(req) as response:
                status = response.getcode()
                response_body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Jira API request failed with status {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Jira API request failed: {exc.reason}") from exc

        if status < 200 or status >= 300:
            raise RuntimeError(f"Jira API request failed with status {status}: {response_body}")
        if not response_body:
            return {}
        return json.loads(response_body)

    def _authorization_header(self) -> str:
        raw = f"{self.config.user_email}:{self.config.api_token}".encode()
        return f"Basic {base64.b64encode(raw).decode('ascii')}"

    @staticmethod
    def _format_description(story: UserStory) -> str:
        criteria = "\n".join(f"- {criterion}" for criterion in story.acceptance_criteria)
        return (
            f"As a {story.as_a}, I want {story.i_want}, so that {story.so_that}.\n\n"
            f"Acceptance Criteria:\n{criteria}"
        )
