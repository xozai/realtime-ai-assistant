from __future__ import annotations

from realtime_assistant.coverage import analyze_coverage
from realtime_assistant.models import DiscoverySession, Requirement


def test_analyze_coverage_counts_low_confidence_requirements() -> None:
    session = DiscoverySession(
        requirements=[
            Requirement(
                id="REQ-001",
                text="Users can log in",
                category="functional",
                confidence="high",
            ),
            Requirement(
                id="REQ-002",
                text="Make login better",
                category="functional",
                confidence="low",
            ),
        ]
    )

    report = analyze_coverage(session)

    assert report.low_confidence_count == 1
