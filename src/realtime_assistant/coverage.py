"""Requirement-to-story coverage analysis (issue #20)."""

from __future__ import annotations

from realtime_assistant.models import (
    CoverageReport,
    CoverageStatus,
    DiscoverySession,
    RequirementCoverage,
)


def analyze_coverage(session: DiscoverySession) -> CoverageReport:
    """Compute a CoverageReport for *session* without calling any external API.

    Each requirement is classified as:
    - ``"no-stories-yet"`` — no user stories have been generated at all.
    - ``"covered"`` — at least one story cites this requirement's ID in
      ``source_requirement_ids``.
    - ``"uncovered"`` — stories exist but none cite this requirement.
    """
    if not session.requirements:
        return CoverageReport()

    has_stories = bool(session.user_stories)

    # Build a map: requirement_id -> list of story IDs that cite it
    citing: dict[str, list[str]] = {req.id: [] for req in session.requirements}
    for story in session.user_stories:
        for req_id in story.source_requirement_ids:
            if req_id in citing:
                citing[req_id].append(story.id)

    items: list[RequirementCoverage] = []
    covered_count = 0
    uncovered_count = 0

    for req in session.requirements:
        story_ids = citing[req.id]
        if not has_stories:
            status: CoverageStatus = "no-stories-yet"
        elif story_ids:
            status = "covered"
            covered_count += 1
        else:
            status = "uncovered"
            uncovered_count += 1

        items.append(
            RequirementCoverage(
                requirement_id=req.id,
                text=req.text,
                category=req.category,
                status=status,
                story_ids=story_ids,
            )
        )

    total = len(session.requirements)
    coverage_pct = round(covered_count / total * 100, 1) if total else 0.0
    low_confidence_count = sum(1 for req in session.requirements if req.confidence == "low")

    return CoverageReport(
        items=items,
        covered_count=covered_count,
        uncovered_count=uncovered_count,
        low_confidence_count=low_confidence_count,
        coverage_pct=coverage_pct,
    )
