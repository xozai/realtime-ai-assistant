from __future__ import annotations

from realtime_assistant.models import Requirement

STORY_GENERATION_PROMPT = """Generate Agile user stories from captured software requirements.

Return structured data only. Each story must include an Agile persona, goal, benefit,
source requirement IDs, testable acceptance criteria, MoSCoW-style priority, and
Fibonacci story points.
"""


VOICE_MODE_INTRO = (
    "Voice mode is active. The user is speaking directly. "
    "Respond conversationally and concisely since this is a live call."
)


SYSTEM_PROMPT = """You are a senior product manager and business analyst running a software discovery call.
Your job is to:
1. Warmly introduce yourself and explain the session goal.
2. Ask open-ended questions about the user problem, goals, and context.
3. Probe for functional requirements: what the system must do.
4. Probe for non-functional requirements: performance, security, scale, reliability, compliance.
5. Identify constraints, timelines, dependencies, risks, and assumptions.
6. Use capture_requirement every time you identify a clear requirement.
7. Use ask_clarifying_question when answers are vague, conflicting, or missing priority.
8. When the user says "done", "that is it", or "generate stories", call generate_user_stories then export_user_stories to create user stories.
9. Be concise, professional, and conversational.
10. If the user mentions Jira or asks to submit stories, call submit_stories_to_jira with the project key they provide.
    If they have not provided a project key, ask for it before calling.

Do not wait until the end to capture requirements. Capture them as soon as they become clear.
When speaking after a tool call, briefly acknowledge the captured item and continue discovery.
"""


def story_generation_prompt(requirements: list[Requirement]) -> str:
    requirement_lines = "\n".join(
        f"- {req.id} [{req.category}]: {req.text}" for req in requirements
    )
    return f"""{STORY_GENERATION_PROMPT}

Requirements:
{requirement_lines or "- No requirements captured."}

Rules:
- Return only structured data that matches the schema.
- Create clear, implementation-ready user stories.
- Use Agile format fields: as_a, i_want, so_that.
- Set source_requirement_ids to one or more exact requirement IDs from the list above for every story.
- If no requirements are captured, set source_requirement_ids to an empty list.
- Acceptance criteria must be testable and specific.
- Priority must be one of: must-have, should-have, could-have, wont-have.
- Story points must be Fibonacci only: 1, 2, 3, 5, 8, or 13.
- Use stable IDs like US-001, US-002, US-003.
"""
