from __future__ import annotations

from realtime_assistant.models import Requirement, UserStory

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
8. Before generating stories, proactively re-ask about low-confidence requirements so vague items are clarified first.
9. When the user says "done", "that is it", or "generate stories", call generate_user_stories then export_user_stories to create user stories.
10. When the user asks to refine or regenerate one existing story, call refine_user_story with the target story ID, feedback, and any selected requirement IDs.
11. Be concise, professional, and conversational.
12. If the user mentions Jira or asks to submit stories, call submit_stories_to_jira with the project key they provide.
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


def story_refinement_prompt(
    story: UserStory,
    requirements: list[Requirement],
    *,
    feedback: str | None = None,
) -> str:
    requirement_lines = "\n".join(
        f"- {req.id} [{req.category}]: {req.text}" for req in requirements
    )
    criteria_lines = "\n".join(
        f"- {criterion}" for criterion in story.acceptance_criteria
    )
    reviewer_feedback = feedback.strip() if feedback and feedback.strip() else "No reviewer feedback provided."
    return f"""Refine or regenerate exactly one Agile user story.

Existing story:
- id: {story.id}
- title: {story.title}
- as_a: {story.as_a}
- i_want: {story.i_want}
- so_that: {story.so_that}
- source_requirement_ids: {", ".join(story.source_requirement_ids) or "(none)"}
- acceptance_criteria:
{criteria_lines or "- (none)"}
- priority: {story.priority}
- story_points: {story.story_points}

Source requirements:
{requirement_lines or "- No source requirements available."}

Reviewer feedback:
{reviewer_feedback}

Rules:
- Return only structured data that matches the UserStory schema.
- Return exactly one story, not a full story set.
- Preserve the existing story id exactly as {story.id}.
- Use Agile format fields: as_a, i_want, so_that.
- Set source_requirement_ids to exact requirement IDs from the source requirements above.
- If no source requirements are available, keep source_requirement_ids empty.
- Acceptance criteria must be testable, specific, and reflect the reviewer feedback.
- Priority must be one of: must-have, should-have, could-have, wont-have.
- Story points must be Fibonacci only: 1, 2, 3, 5, 8, or 13.
"""
