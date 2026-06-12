from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from urllib import error, request

from realtime_assistant.logging import logger


@dataclass(frozen=True)
class NotificationResult:
    notifier: str
    enabled: bool
    sent: bool
    error: str | None = None


class Notifier(ABC):
    """Base class for incoming-webhook notification targets."""

    name: str
    env_var: str

    def __init__(self, webhook_url: str | None = None) -> None:
        self.webhook_url = webhook_url if webhook_url is not None else os.getenv(self.env_var)

    @property
    def enabled(self) -> bool:
        return bool(self.webhook_url)

    def notify(
        self,
        *,
        story_count: int,
        requirement_count: int,
        export_paths: list[str] | None = None,
        jira_keys: list[str] | None = None,
    ) -> NotificationResult:
        if not self.webhook_url:
            return NotificationResult(notifier=self.name, enabled=False, sent=False)

        payload = self.payload(
            story_count=story_count,
            requirement_count=requirement_count,
            export_paths=export_paths or [],
            jira_keys=jira_keys or [],
        )
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            self.webhook_url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with request.urlopen(req, timeout=5) as response:
                status = response.getcode()
                response_body = response.read().decode("utf-8", errors="replace")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{self.name} notification failed with status {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"{self.name} notification failed: {exc.reason}") from exc

        if status < 200 or status >= 300:
            raise RuntimeError(
                f"{self.name} notification failed with status {status}: {response_body}"
            )
        return NotificationResult(notifier=self.name, enabled=True, sent=True)

    @abstractmethod
    def payload(
        self,
        *,
        story_count: int,
        requirement_count: int,
        export_paths: list[str],
        jira_keys: list[str],
    ) -> dict[str, object]:
        """Return the webhook JSON payload."""


class SlackNotifier(Notifier):
    name = "slack"
    env_var = "SLACK_WEBHOOK_URL"

    def payload(
        self,
        *,
        story_count: int,
        requirement_count: int,
        export_paths: list[str],
        jira_keys: list[str],
    ) -> dict[str, object]:
        return {
            "text": format_story_ready_message(
                story_count,
                requirement_count,
                export_paths,
                jira_keys,
            )
        }


class TeamsNotifier(Notifier):
    name = "teams"
    env_var = "TEAMS_WEBHOOK_URL"

    def payload(
        self,
        *,
        story_count: int,
        requirement_count: int,
        export_paths: list[str],
        jira_keys: list[str],
    ) -> dict[str, object]:
        return {
            "text": format_story_ready_message(
                story_count,
                requirement_count,
                export_paths,
                jira_keys,
            )
        }


def format_story_ready_message(
    story_count: int,
    requirement_count: int,
    export_paths: list[str] | None = None,
    jira_keys: list[str] | None = None,
) -> str:
    paths = export_paths or []
    keys = jira_keys or []
    return "\n".join(
        [
            "User stories ready.",
            f"Stories: {story_count}",
            f"Requirements: {requirement_count}",
            f"Exports: {', '.join(paths) if paths else 'None'}",
            f"Jira keys: {', '.join(keys) if keys else 'None'}",
        ]
    )


def configured_notifiers() -> list[Notifier]:
    return [SlackNotifier(), TeamsNotifier()]


def notify_story_ready(
    *,
    story_count: int,
    requirement_count: int,
    export_paths: list[str] | None = None,
    jira_keys: list[str] | None = None,
    notifiers: list[Notifier] | None = None,
) -> list[NotificationResult]:
    results: list[NotificationResult] = []
    for notifier in configured_notifiers() if notifiers is None else notifiers:
        try:
            results.append(
                notifier.notify(
                    story_count=story_count,
                    requirement_count=requirement_count,
                    export_paths=export_paths,
                    jira_keys=jira_keys,
                )
            )
        except Exception as exc:
            logger.warning("Failed to send %s notification: %s", notifier.name, exc)
            results.append(
                NotificationResult(
                    notifier=notifier.name,
                    enabled=True,
                    sent=False,
                    error=str(exc),
                )
            )
    return results
