from __future__ import annotations

import logging

from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table

from realtime_assistant.models import Requirement, UserStory

console = Console()


def configure_logging() -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        handlers=[RichHandler(console=console, show_path=False, rich_tracebacks=True)],
    )
    return logging.getLogger("realtime_assistant")


logger = configure_logging()


def log_requirement(requirement: Requirement) -> None:
    table = Table.grid(padding=(0, 1))
    table.add_column(style="bold cyan")
    table.add_column()
    table.add_row("ID", requirement.id)
    table.add_row("Category", requirement.category)
    table.add_row("Text", requirement.text)
    console.print(Panel(table, title="Requirement Captured", border_style="green"))


def log_clarifying_question(topic: str, question: str) -> None:
    console.print(
        Panel(
            f"[bold]Topic:[/bold] {topic}\n[bold]Question:[/bold] {question}",
            title="Clarifying Question",
            border_style="yellow",
        )
    )


def log_stories(stories: list[UserStory]) -> None:
    table = Table(title="Generated User Stories", header_style="bold magenta")
    table.add_column("ID", style="cyan")
    table.add_column("Title")
    table.add_column("Priority")
    table.add_column("Points", justify="right")
    for story in stories:
        table.add_row(story.id, story.title, story.priority, str(story.story_points))
    console.print(table)
