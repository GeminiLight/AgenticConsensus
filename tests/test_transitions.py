from datetime import UTC, datetime, timedelta

import pytest

from system.domain.models import DecisionAction, Evidence, Finding, ReviewPackage
from system.domain.transitions import DecisionBlocked, decide


def ready_review(**overrides):
    values = {
        "id": "review-1",
        "project_id": "project-1",
        "base_ref": "base",
        "target_ref": "target",
        "base_version": 1,
        "current_project_version": 1,
        "status": "open",
        "evidence": [
            Evidence(kind="static_analysis", status="pass", summary="AST complete"),
            Evidence(kind="tests", status="pass", summary="4 passed"),
        ],
        "findings": [],
    }
    values.update(overrides)
    return ReviewPackage(**values)


def test_commit_requires_current_base_and_complete_evidence():
    review = ready_review(current_project_version=2)
    with pytest.raises(DecisionBlocked, match="stale base"):
        decide(review, DecisionAction(action="commit", actor="lead@example.test"))

    missing_tests = ready_review(evidence=[Evidence(kind="static_analysis", status="pass", summary="ok")])
    with pytest.raises(DecisionBlocked, match="tests evidence"):
        decide(missing_tests, DecisionAction(action="commit", actor="lead@example.test"))


def test_open_critical_and_unobservable_findings_block_commit():
    for kind in ("forbidden_dependency", "unobservable"):
        review = ready_review(
            findings=[Finding(rule_id="billing-boundary", kind=kind, severity="critical", message="risk")]
        )
        with pytest.raises(DecisionBlocked, match="critical"):
            decide(review, DecisionAction(action="commit", actor="lead@example.test"))


def test_waiver_requires_bounded_human_justification():
    review = ready_review(
        findings=[Finding(id="finding-1", rule_id="billing-boundary", kind="forbidden_dependency", severity="critical", message="risk")]
    )
    with pytest.raises(DecisionBlocked, match="reason"):
        decide(review, DecisionAction(action="waive", actor="lead@example.test", finding_ids=["finding-1"]))

    result = decide(
        review,
        DecisionAction(
            action="waive",
            actor="lead@example.test",
            reason="Time-bounded migration bridge",
            scope="services.checkout.billing_adapter",
            expires_at=datetime.now(UTC) + timedelta(days=7),
            finding_ids=["finding-1"],
        ),
    )
    assert result.review.findings[0].status == "waived"
    assert result.review.status == "open"
    assert result.event.action == "waive"


def test_commit_and_rollback_create_explicit_transitions():
    committed = decide(ready_review(), DecisionAction(action="commit", actor="lead@example.test"))
    assert committed.review.status == "committed"
    assert committed.new_project_version == 2

    rolled_back = decide(
        committed.review,
        DecisionAction(action="rollback", actor="lead@example.test", reason="Production evidence invalidated the change"),
    )
    assert rolled_back.review.status == "rolled_back"
    assert rolled_back.new_project_version == 3
