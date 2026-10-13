from datetime import UTC, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, current_thread, main_thread

import pytest

from system.domain.models import AuditEvent, AuthorityGrant, DecisionAction, Evidence, StructuralClaim
from system.domain.transitions import DecisionBlocked
from system.services.database import ConcurrentTransitionError, Database
from system.services.review_service import DuplicateReviewError, ReviewService
from tests.helpers import create_alternate_target, create_billing_repo, create_capability_repo


def test_real_git_review_persists_evidence_findings_and_human_events(tmp_path: Path):
    repo, base, target = create_billing_repo(tmp_path)
    database = Database(tmp_path / "control.db")
    service = ReviewService(database)
    project = service.create_project(
        name="Billing boundary",
        repo_path=repo,
        head_ref=base,
        test_command=["python3", "-m", "unittest", "-q"],
        claims=[
            StructuralClaim(
                id="billing.no_new_legacy_reads",
                title="No new legacy billing reads",
                forbidden_modules=["legacy.billing"],
                rationale="Checkout must use the new billing API.",
            )
        ],
    )
    review = service.create_review(project.id, base_ref=base, target_ref=target)

    assert {item.kind: item.status for item in review.evidence}["tests"] == "pass"
    assert "tests passed" in review.summary.lower()
    assert "finding(s)" not in review.summary
    assert "relation(s)" not in next(item for item in review.evidence if item.kind == "static_analysis").summary
    assert any(item.kind == "forbidden_dependency" and item.status == "open" for item in review.findings)
    with pytest.raises(DecisionBlocked, match="critical"):
        service.decide(review.id, DecisionAction(action="commit", actor="tech-lead"))

    finding_id = review.findings[0].id
    waived = service.decide(
        review.id,
        DecisionAction(
            action="waive",
            actor="tech-lead",
            reason="Migration bridge while the new invoice endpoint stabilizes",
            scope="checkout.total",
            expires_at=datetime.now(UTC) + timedelta(days=7),
            finding_ids=[finding_id],
        ),
    )
    assert waived.findings[0].status == "waived"
    committed = service.decide(review.id, DecisionAction(action="commit", actor="tech-lead"))
    assert committed.status == "committed"
    assert "open critical" not in committed.summary.lower()
    assert "committed" in committed.summary.lower()
    assert database.get_project(project.id).version == 2
    assert [event.action for event in database.list_events(review.id)] == ["create_review", "waive", "commit"]


def test_second_review_becomes_stale_after_first_commit(tmp_path: Path):
    repo, base, target = create_billing_repo(tmp_path)
    second_target = create_alternate_target(
        repo,
        base,
        path="shipping.py",
        content="def destination(value):\n    return value.strip()\n",
        message="independent shipping proposal",
    )
    database = Database(tmp_path / "control.db")
    service = ReviewService(database)
    project = service.create_project(
        name="Concurrent work",
        repo_path=repo,
        head_ref=base,
        test_command=["python3", "-m", "unittest", "-q"],
        claims=[],
    )
    first = service.create_review(project.id, base_ref=base, target_ref=target)
    second = service.create_review(project.id, base_ref=base, target_ref=second_target)
    service.decide(first.id, DecisionAction(action="commit", actor="lead"))

    with pytest.raises(DecisionBlocked, match="stale base"):
        service.decide(second.id, DecisionAction(action="commit", actor="lead"))


def test_concurrent_duplicate_review_creation_admits_only_one(tmp_path: Path, monkeypatch):
    repo, base, target = create_billing_repo(tmp_path)
    database = Database(tmp_path / "concurrent-review-create.db")
    service = ReviewService(database)
    project = service.create_project(
        name="Atomic review creation",
        repo_path=repo,
        head_ref=base,
        test_command=[],
        claims=[],
    )
    original_list_reviews = database.list_reviews
    both_requests_passed_duplicate_read = Barrier(2)

    def synchronized_list_reviews(project_id=None):
        reviews = original_list_reviews(project_id)
        if current_thread() is not main_thread() and not reviews:
            both_requests_passed_duplicate_read.wait(timeout=5)
        return reviews

    monkeypatch.setattr(database, "list_reviews", synchronized_list_reviews)

    def create():
        try:
            return "created", service.create_review(
                project.id, base_ref=base, target_ref=target
            )
        except DuplicateReviewError as exc:
            return "duplicate", str(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: create(), range(2)))

    assert [status for status, _ in outcomes].count("created") == 1
    assert [status for status, _ in outcomes].count("duplicate") == 1
    assert len(original_list_reviews(project.id)) == 1
    stored = original_list_reviews(project.id)[0]
    assert [event.action for event in database.list_events(stored.id)] == [
        "create_review"
    ]


def test_rerun_tests_preserves_a_concurrent_project_update(tmp_path: Path, monkeypatch):
    repo, base, target = create_billing_repo(tmp_path)
    database = Database(tmp_path / "concurrent-test-rerun.db")
    service = ReviewService(database)
    project = service.create_project(
        name="Atomic test evidence",
        repo_path=repo,
        head_ref=base,
        test_command=[],
        claims=[],
    )
    review = service.create_review(project.id, base_ref=base, target_ref=target)

    def run_after_project_change(*_args, **_kwargs):
        concurrent_project = database.get_project(project.id)
        concurrent_project.default_authority = "concurrent policy owner"
        database.save_project(concurrent_project)
        return Evidence(kind="tests", status="pass", summary="Test command exited 0")

    monkeypatch.setattr("system.services.review_service.run_tests", run_after_project_change)

    updated = service.rerun_tests(
        review.id,
        test_command=["python3", "-m", "unittest", "-q"],
        actor="lead",
    )

    stored_project = database.get_project(project.id)
    assert stored_project.default_authority == "concurrent policy owner"
    assert stored_project.test_command == []
    assert updated.revision == review.revision + 1
    assert [event.action for event in database.list_events(review.id)] == [
        "create_review",
        "rerun_tests",
    ]


def test_rerun_tests_rejects_invalid_or_closed_review_requests(tmp_path: Path):
    repo, base, target = create_billing_repo(tmp_path)
    database = Database(tmp_path / "guarded-test-rerun.db")
    service = ReviewService(database)
    project = service.create_project(
        name="Guarded test evidence",
        repo_path=repo,
        head_ref=base,
        test_command=[],
        claims=[],
    )
    review = service.create_review(project.id, base_ref=base, target_ref=target)

    with pytest.raises(DecisionBlocked, match="non-empty test command"):
        service.rerun_tests(review.id, test_command=[], actor="lead")

    rejected = service.decide(
        review.id,
        DecisionAction(
            action="reject",
            actor="lead",
            reason="The proposal is intentionally closed before tests are rerun",
        ),
    )
    with pytest.raises(DecisionBlocked, match="rejected status"):
        service.rerun_tests(
            rejected.id,
            test_command=["python3", "-m", "unittest", "-q"],
            actor="lead",
        )
    assert database.get_project(project.id).test_command == []


def test_rerun_tests_records_failed_target_evidence(tmp_path: Path):
    repo, base, target = create_billing_repo(tmp_path)
    database = Database(tmp_path / "failed-test-rerun.db")
    service = ReviewService(database)
    project = service.create_project(
        name="Failed test evidence",
        repo_path=repo,
        head_ref=base,
        test_command=[],
        claims=[],
    )
    review = service.create_review(project.id, base_ref=base, target_ref=target)

    updated = service.rerun_tests(
        review.id,
        test_command=["python3", "-c", "raise SystemExit(7)"],
        actor="lead",
    )

    evidence = next(item for item in updated.evidence if item.kind == "tests")
    assert evidence.status == "fail"
    assert evidence.outcome == "contests"
    assert evidence.artifact_ref == review.target_ref
    assert evidence.details["exit_code"] == 7
    assert database.get_project(project.id).test_command == []


def test_rerun_tests_cannot_replace_the_project_test_command(tmp_path: Path):
    repo, base, target = create_billing_repo(tmp_path)
    database = Database(tmp_path / "fixed-test-command.db")
    service = ReviewService(database)
    project = service.create_project(
        name="Fixed test command",
        repo_path=repo,
        head_ref=base,
        test_command=["python3", "-m", "unittest", "-q"],
        claims=[],
    )
    review = service.create_review(project.id, base_ref=base, target_ref=target)

    with pytest.raises(DecisionBlocked, match="cannot be replaced mid-review"):
        service.rerun_tests(
            review.id,
            test_command=["python3", "-c", "pass"],
            actor="lead",
        )

    assert database.get_project(project.id).test_command == [
        "python3",
        "-m",
        "unittest",
        "-q",
    ]
    assert database.get_review(review.id).revision == review.revision
    assert [event.action for event in database.list_events(review.id)] == [
        "create_review"
    ]


def test_rerun_tests_revision_race_leaves_project_and_evidence_unchanged(
    tmp_path: Path, monkeypatch
):
    repo, base, target = create_billing_repo(tmp_path)
    database = Database(tmp_path / "stale-test-rerun.db")
    service = ReviewService(database)
    project = service.create_project(
        name="Stale test evidence",
        repo_path=repo,
        head_ref=base,
        test_command=[],
        claims=[],
    )
    review = service.create_review(project.id, base_ref=base, target_ref=target)

    def run_after_review_change(*_args, **_kwargs):
        competing = database.get_review(review.id)
        expected_revision = competing.revision
        competing.revision += 1
        competing.updated_at = datetime.now(UTC)
        database.apply_review_transition(
            review=competing,
            event=AuditEvent(
                review_id=review.id,
                action="summarize",
                actor="system",
            ),
            expected_review_revision=expected_revision,
        )
        return Evidence(kind="tests", status="pass", summary="Test command exited 0")

    monkeypatch.setattr("system.services.review_service.run_tests", run_after_review_change)

    with pytest.raises(ConcurrentTransitionError, match="concurrent review update"):
        service.rerun_tests(
            review.id,
            test_command=["python3", "-m", "unittest", "-q"],
            actor="lead",
        )

    assert database.get_project(project.id).test_command == []
    stored = database.get_review(review.id)
    assert stored.revision == review.revision + 1
    assert next(item for item in stored.evidence if item.kind == "tests").status == "not_run"
    assert [event.action for event in database.list_events(review.id)] == [
        "create_review",
        "summarize",
    ]


def test_concurrent_commits_from_the_same_project_version_admit_only_one(tmp_path: Path, monkeypatch):
    repo, base, target = create_billing_repo(tmp_path)
    second_target = create_alternate_target(
        repo,
        base,
        path="shipping.py",
        content="def destination(value):\n    return value.strip()\n",
        message="independent shipping proposal",
    )
    database = Database(tmp_path / "concurrent-control.db")
    service = ReviewService(database)
    project = service.create_project(
        name="Atomic transitions",
        repo_path=repo,
        head_ref=base,
        test_command=["python3", "-m", "unittest", "-q"],
        claims=[],
    )
    first = service.create_review(project.id, base_ref=base, target_ref=target)
    second = service.create_review(project.id, base_ref=base, target_ref=second_target)

    original_get_project = database.get_project
    both_requests_loaded_version_one = Barrier(2)

    def synchronized_get_project(project_id: str):
        loaded = original_get_project(project_id)
        if current_thread() is not main_thread():
            both_requests_loaded_version_one.wait(timeout=5)
        return loaded

    monkeypatch.setattr(database, "get_project", synchronized_get_project)

    def commit(review_id: str):
        try:
            return "committed", service.decide(
                review_id, DecisionAction(action="commit", actor="lead")
            )
        except DecisionBlocked as exc:
            return "blocked", str(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(commit, [first.id, second.id]))

    assert [status for status, _ in outcomes].count("committed") == 1
    assert [status for status, _ in outcomes].count("blocked") == 1
    assert "concurrent project-state update" in next(
        detail for status, detail in outcomes if status == "blocked"
    )
    assert original_get_project(project.id).version == 2
    stored_reviews = [database.get_review(first.id), database.get_review(second.id)]
    assert sum(review.status == "committed" for review in stored_reviews) == 1
    assert sum(
        event.action == "commit"
        for review in stored_reviews
        for event in database.list_events(review.id)
    ) == 1


def test_concurrent_dispositions_on_one_review_do_not_overwrite_each_other(tmp_path: Path, monkeypatch):
    repo, base, target = create_billing_repo(tmp_path)
    database = Database(tmp_path / "concurrent-review.db")
    service = ReviewService(database)
    project = service.create_project(
        name="Atomic review disposition",
        repo_path=repo,
        head_ref=base,
        test_command=["python3", "-m", "unittest", "-q"],
        claims=[
            StructuralClaim(
                id="billing.no_new_legacy_reads",
                title="No new legacy billing reads",
                forbidden_modules=["legacy.billing"],
            )
        ],
    )
    review = service.create_review(project.id, base_ref=base, target_ref=target)
    finding_id = review.findings[0].id

    original_get_review = database.get_review
    both_requests_loaded_revision_one = Barrier(2)

    def synchronized_get_review(review_id: str):
        loaded = original_get_review(review_id)
        if current_thread() is not main_thread():
            both_requests_loaded_revision_one.wait(timeout=5)
        return loaded

    monkeypatch.setattr(database, "get_review", synchronized_get_review)

    def waive(reason: str):
        try:
            return "waived", service.decide(
                review.id,
                DecisionAction(
                    action="waive",
                    actor="lead",
                    reason=reason,
                    scope="checkout.total",
                    expires_at=datetime.now(UTC) + timedelta(days=7),
                    finding_ids=[finding_id],
                ),
            )
        except DecisionBlocked as exc:
            return "blocked", str(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(
            pool.map(
                waive,
                [
                    "Temporary migration exception approved by billing lead",
                    "Parallel exception request must not replace the first decision",
                ],
            )
        )

    assert [status for status, _ in outcomes].count("waived") == 1
    assert [status for status, _ in outcomes].count("blocked") == 1
    assert "concurrent review update" in next(
        detail for status, detail in outcomes if status == "blocked"
    )
    stored = original_get_review(review.id)
    assert stored.revision == 2
    assert len(stored.waivers) == 1
    assert [event.action for event in database.list_events(review.id)] == ["create_review", "waive"]


def test_tests_run_against_target_commit_not_dirty_worktree(tmp_path: Path):
    repo, base, target = create_billing_repo(tmp_path)
    (repo / "test_checkout.py").write_text("raise RuntimeError('dirty working tree must be ignored')\n", encoding="utf-8")
    database = Database(tmp_path / "control.db")
    service = ReviewService(database)
    project = service.create_project(
        name="Immutable test target",
        repo_path=repo,
        head_ref=base,
        test_command=["python3", "-m", "unittest", "-q"],
        claims=[],
    )
    review = service.create_review(project.id, base_ref=base, target_ref=target)
    assert next(item for item in review.evidence if item.kind == "tests").status == "pass"


def test_overlapping_open_proposals_are_visible(tmp_path: Path):
    repo, base, target = create_billing_repo(tmp_path)
    second_target = create_alternate_target(
        repo,
        base,
        path="checkout.py",
        content="def total(value):\n    return value + value\n",
        message="alternate checkout proposal",
    )
    database = Database(tmp_path / "control.db")
    service = ReviewService(database)
    project = service.create_project(
        name="Overlap",
        repo_path=repo,
        head_ref=base,
        test_command=["python3", "-m", "unittest", "-q"],
        claims=[],
    )
    first = service.create_review(project.id, base_ref=base, target_ref=target)
    second = service.create_review(project.id, base_ref=base, target_ref=second_target)
    overlap = next(item for item in second.findings if item.kind == "overlap")
    assert first.id in overlap.details["reviews"]
    assert "checkout.py" in overlap.details["paths"]


def test_rollback_marks_prior_evidence_historical(tmp_path: Path):
    repo, base, target = create_billing_repo(tmp_path)
    database = Database(tmp_path / "control.db")
    service = ReviewService(database)
    project = service.create_project(
        name="Rollback",
        repo_path=repo,
        head_ref=base,
        test_command=["python3", "-m", "unittest", "-q"],
        claims=[],
    )
    review = service.create_review(project.id, base_ref=base, target_ref=target)
    committed = service.decide(review.id, DecisionAction(action="commit", actor="lead"))
    rolled_back = service.decide(
        committed.id,
        DecisionAction(action="rollback", actor="lead", reason="New production evidence invalidates the transition"),
    )
    assert rolled_back.status == "rolled_back"
    assert any(item.kind == "policy" and item.status == "unknown" for item in rolled_back.evidence)
    assert database.get_project(project.id).version == 3


def test_committed_manifest_reports_an_admitted_transition_not_a_new_blocker(tmp_path: Path):
    repo, base, target = create_billing_repo(tmp_path)
    service = ReviewService(Database(tmp_path / "committed-manifest.db"))
    project = service.create_project(
        name="Historical admission",
        repo_path=repo,
        head_ref=base,
        test_command=["python3", "-m", "unittest", "-q"],
        claims=[],
    )
    review = service.create_review(project.id, base_ref=base, target_ref=target)
    committed = service.decide(review.id, DecisionAction(action="commit", actor="lead"))

    manifest = service.get_change_package(committed.id)

    assert manifest.gate_state == "committed"
    assert manifest.committable is False
    assert manifest.blockers == []
    base_check = next(item for item in manifest.admission_checks if item.key == "base_version")
    assert base_check.status == "pass"
    assert base_check.summary == "Transition was admitted from C^1 to C^2"


def test_review_exposes_claim_delta_anchors_and_evidence_lifecycle(tmp_path: Path):
    repo, base, target = create_billing_repo(tmp_path)
    service = ReviewService(Database(tmp_path / "package.db"))
    project = service.create_project(
        name="Billing boundary",
        repo_path=repo,
        head_ref=base,
        test_command=["python3", "-m", "unittest", "-q"],
        claims=[
            StructuralClaim(
                id="billing.no_new_legacy_reads",
                title="No new legacy billing reads",
                scope="checkout.*",
                introduced_version=3,
                forbidden_modules=["legacy.billing"],
                artifact_anchors=[{"path": "checkout.py", "kind": "code", "relation": "realizes"}],
                evidence_obligations=["static import boundary", "target test suite"],
                authority="billing platform owner",
            )
        ],
    )
    review = service.create_review(
        project.id,
        base_ref=base,
        target_ref=target,
        proposer="coding-agent/archive-migration",
        intent_summary="Reuse the legacy rate while extracting checkout",
    )

    assert review.intent_summary.startswith("Reuse")
    assert review.proposer == "coding-agent/archive-migration"
    assert review.changed_paths == ["checkout.py"]
    delta = review.claim_deltas[0]
    assert delta.claim_id == "billing.no_new_legacy_reads"
    assert delta.status == "contested"
    assert delta.source == "rehydrated"
    assert delta.artifact_anchors[0].path == "checkout.py"

    static = next(item for item in review.evidence if item.kind == "static_analysis")
    assert static.status == "pass"
    assert static.outcome == "contests"
    assert static.claim_ids == ["billing.no_new_legacy_reads"]
    assert static.artifact_ref == target
    assert static.provenance == "python_ast"
    assert static.freshness == "current"


def test_unobservable_relation_is_inconclusive_and_manifest_blocks_commit(tmp_path: Path):
    repo, base, target = create_capability_repo(tmp_path)
    service = ReviewService(Database(tmp_path / "unobservable.db"))
    project = service.create_project(
        name="Capability migration",
        repo_path=repo,
        head_ref=base,
        test_command=["python3", "-m", "unittest", "-q"],
        claims=[
            StructuralClaim(
                id="authority.task_scoped_only",
                title="Connectors use only task-scoped capabilities",
                forbidden_modules=["legacy.workspace_credentials"],
            )
        ],
    )
    review = service.create_review(project.id, base_ref=base, target_ref=target)
    manifest = service.get_change_package(review.id)

    assert any(item.kind == "unobservable" for item in review.findings)
    static = next(item for item in review.evidence if item.kind == "static_analysis")
    assert static.status == "pass"
    assert static.outcome == "inconclusive"
    assert manifest.notation == {
        "v_t": 1,
        "delta_c": 1,
        "delta_a": 3,
        "delta_e": 3,
        "unresolved": 1,
        "waivers": 0,
    }
    assert manifest.committable is False
    assert any(item.key == "critical_findings" and item.status == "block" for item in manifest.admission_checks)


def test_declared_evidence_obligation_is_frozen_and_blocks_commit_after_finding_waiver(tmp_path: Path):
    repo, base, target = create_billing_repo(tmp_path)
    service = ReviewService(Database(tmp_path / "obligation-block.db"))
    project = service.create_project(
        name="Evidence-gated billing",
        repo_path=repo,
        head_ref=base,
        test_command=["python3", "-m", "unittest", "-q"],
        claims=[
            StructuralClaim(
                id="billing.no_new_legacy_reads",
                title="No new legacy billing reads",
                forbidden_modules=["legacy.billing"],
                evidence_obligations=["credential provenance for the target revision"],
            )
        ],
    )
    review = service.create_review(project.id, base_ref=base, target_ref=target)

    assert len(review.evidence_obligations) == 1
    obligation = review.evidence_obligations[0]
    assert obligation.claim_id == "billing.no_new_legacy_reads"
    assert obligation.label == "credential provenance for the target revision"
    assert obligation.evidence_kind == "attestation"

    waived = service.decide(
        review.id,
        DecisionAction(
            action="waive",
            actor="lead",
            reason="Temporary dependency exception while provenance is collected",
            scope="checkout.total",
            expires_at=datetime.now(UTC) + timedelta(days=7),
            finding_ids=[review.findings[0].id],
        ),
    )
    manifest = service.get_change_package(waived.id)
    obligation_check = next(
        item for item in manifest.admission_checks if item.key == "evidence_obligations"
    )
    assert obligation_check.status == "block"
    assert manifest.obligation_statuses[0].status == "missing"

    with pytest.raises(DecisionBlocked, match="evidence obligation"):
        service.decide(waived.id, DecisionAction(action="commit", actor="lead"))


def test_authorized_current_attestation_satisfies_an_explicit_obligation(tmp_path: Path):
    repo, base, target = create_billing_repo(tmp_path)
    database = Database(tmp_path / "obligation-satisfied.db")
    service = ReviewService(database)
    project = service.create_project(
        name="Attested billing change",
        repo_path=repo,
        head_ref=base,
        test_command=["python3", "-m", "unittest", "-q"],
        claims=[
            StructuralClaim(
                id="billing.no_new_legacy_reads",
                title="No new legacy billing reads",
                forbidden_modules=["legacy.billing"],
                evidence_obligations=["credential provenance for the target revision"],
            )
        ],
    )
    review = service.create_review(project.id, base_ref=base, target_ref=target)
    obligation = review.evidence_obligations[0]

    attached = service.attach_evidence(
        review.id,
        actor="billing-lead",
        authority="local operator",
        policy_id="local-single-user/v1",
        obligation_ids=[obligation.id],
        summary="Credential provenance trace passed for the proposed revision",
        provenance="runtime_attestation/credential-provenance-042",
    )

    evidence = attached.evidence[-1]
    assert evidence.kind == "attestation"
    assert evidence.status == "pass"
    assert evidence.outcome == "supports"
    assert evidence.obligation_ids == [obligation.id]
    assert evidence.claim_ids == ["billing.no_new_legacy_reads"]
    assert evidence.artifact_ref == target
    assert evidence.recorded_by == "billing-lead"
    assert evidence.authority == "local operator"
    assert evidence.policy_id == "local-single-user/v1"
    assert attached.revision == 2

    manifest = service.get_change_package(review.id)
    assert manifest.obligation_statuses[0].status == "satisfied"
    assert manifest.obligation_statuses[0].evidence_ids == [evidence.id]

    waived = service.decide(
        review.id,
        DecisionAction(
            action="waive",
            actor="billing-lead",
            reason="Temporary dependency exception while the migration completes",
            scope="checkout.total",
            expires_at=datetime.now(UTC) + timedelta(days=7),
            finding_ids=[review.findings[0].id],
        ),
    )
    committed = service.decide(waived.id, DecisionAction(action="commit", actor="billing-lead"))
    assert committed.status == "committed"
    assert [event.action for event in database.list_events(review.id)] == [
        "create_review",
        "attach_evidence",
        "waive",
        "commit",
    ]


def test_attestation_is_enforced_by_the_project_authority_grant(tmp_path: Path):
    repo, base, target = create_billing_repo(tmp_path)
    service = ReviewService(Database(tmp_path / "attest-authority.db"))
    project = service.create_project(
        name="Governed attestation",
        repo_path=repo,
        head_ref=base,
        test_command=["python3", "-m", "unittest", "-q"],
        policy_id="billing-change-control/v1",
        default_authority="security owner",
        authority_grants=[
            AuthorityGrant(
                authority="security owner",
                actors=["alice"],
                actions=["commit", "waive", "attest"],
            )
        ],
        claims=[
            StructuralClaim(
                id="billing.no_new_legacy_reads",
                title="No new legacy billing reads",
                forbidden_modules=["legacy.billing"],
                evidence_obligations=["credential provenance for the target revision"],
                authority="security owner",
            )
        ],
    )
    review = service.create_review(project.id, base_ref=base, target_ref=target)
    obligation_id = review.evidence_obligations[0].id

    with pytest.raises(DecisionBlocked, match="bob.*not authorized.*attest"):
        service.attach_evidence(
            review.id,
            actor="bob",
            authority="security owner",
            policy_id="billing-change-control/v1",
            obligation_ids=[obligation_id],
            summary="Credential provenance trace passed for the target revision",
            provenance="runtime_attestation/credential-provenance-043",
        )

    attached = service.attach_evidence(
        review.id,
        actor="alice",
        authority="security owner",
        policy_id="billing-change-control/v1",
        obligation_ids=[obligation_id],
        summary="Credential provenance trace passed for the target revision",
        provenance="runtime_attestation/credential-provenance-043",
    )
    assert attached.evidence[-1].recorded_by == "alice"
    assert service.get_change_package(review.id).obligation_statuses[0].status == "satisfied"


def test_attestation_must_match_the_obligations_required_provenance(tmp_path: Path):
    repo, base, target = create_billing_repo(tmp_path)
    database = Database(tmp_path / "attest-provenance.db")
    service = ReviewService(database)
    project = service.create_project(
        name="Provenance constrained evidence",
        repo_path=repo,
        head_ref=base,
        test_command=["python3", "-m", "unittest", "-q"],
        claims=[
            StructuralClaim(
                id="billing.no_new_legacy_reads",
                title="No new legacy billing reads",
                forbidden_modules=["legacy.billing"],
                evidence_obligations=[
                    {
                        "label": "credential provenance for the target revision",
                        "required_provenance_prefix": "trusted-runner/credential-trace/",
                    }
                ],
            )
        ],
    )
    review = service.create_review(project.id, base_ref=base, target_ref=target)
    obligation = review.evidence_obligations[0]
    assert obligation.required_provenance_prefix == "trusted-runner/credential-trace/"

    with pytest.raises(DecisionBlocked, match="provenance"):
        service.attach_evidence(
            review.id,
            actor="billing-lead",
            authority="local operator",
            policy_id="local-single-user/v1",
            obligation_ids=[obligation.id],
            summary="A local trace claims the credential boundary passed",
            provenance="developer-laptop/unverified-trace/001",
        )
    assert database.get_review(review.id).revision == 1
    assert [event.action for event in database.list_events(review.id)] == ["create_review"]

    attached = service.attach_evidence(
        review.id,
        actor="billing-lead",
        authority="local operator",
        policy_id="local-single-user/v1",
        obligation_ids=[obligation.id],
        summary="Trusted credential trace passed for the target revision",
        provenance="trusted-runner/credential-trace/001",
    )
    assert attached.revision == 2
    assert service.get_change_package(review.id).obligation_statuses[0].status == "satisfied"


def test_waiver_can_target_one_waivable_evidence_obligation(tmp_path: Path):
    repo, base, target = create_billing_repo(tmp_path)
    service = ReviewService(Database(tmp_path / "obligation-waiver.db"))
    project = service.create_project(
        name="Waivable evidence obligation",
        repo_path=repo,
        head_ref=base,
        test_command=["python3", "-m", "unittest", "-q"],
        claims=[
            StructuralClaim(
                id="billing.no_new_legacy_reads",
                title="No new legacy billing reads",
                forbidden_modules=["legacy.billing"],
                evidence_obligations=[
                    {
                        "label": "credential provenance for the target revision",
                        "waivable": True,
                    }
                ],
            )
        ],
    )
    review = service.create_review(project.id, base_ref=base, target_ref=target)
    obligation = review.evidence_obligations[0]
    assert obligation.waivable is True

    waived = service.decide(
        review.id,
        DecisionAction(
            action="waive",
            actor="billing-lead",
            reason="Temporary provenance outage approved during the migration window",
            scope="billing.no_new_legacy_reads",
            expires_at=datetime.now(UTC) + timedelta(days=2),
            obligation_ids=[obligation.id],
        ),
    )

    assert waived.waivers[-1].finding_ids == []
    assert waived.waivers[-1].obligation_ids == [obligation.id]
    status = service.get_change_package(review.id).obligation_statuses[0]
    assert status.status == "waived"
    assert status.waiver_ids == [waived.waivers[-1].id]
    obligation_check = next(
        item
        for item in service.get_change_package(review.id).admission_checks
        if item.key == "evidence_obligations"
    )
    assert obligation_check.summary == "All declared evidence obligations are satisfied or waived"


def test_nonwaivable_evidence_obligation_rejects_a_waiver(tmp_path: Path):
    repo, base, target = create_billing_repo(tmp_path)
    database = Database(tmp_path / "nonwaivable-obligation.db")
    service = ReviewService(database)
    project = service.create_project(
        name="Mandatory evidence obligation",
        repo_path=repo,
        head_ref=base,
        test_command=["python3", "-m", "unittest", "-q"],
        claims=[
            StructuralClaim(
                id="billing.no_new_legacy_reads",
                title="No new legacy billing reads",
                forbidden_modules=["legacy.billing"],
                evidence_obligations=[
                    {
                        "label": "mandatory credential provenance",
                        "waivable": False,
                    }
                ],
            )
        ],
    )
    review = service.create_review(project.id, base_ref=base, target_ref=target)
    obligation = review.evidence_obligations[0]
    assert obligation.waivable is False

    with pytest.raises(DecisionBlocked, match="not waivable"):
        service.decide(
            review.id,
            DecisionAction(
                action="waive",
                actor="billing-lead",
                reason="Attempted exception for a mandatory provenance requirement",
                scope="billing.no_new_legacy_reads",
                expires_at=datetime.now(UTC) + timedelta(days=2),
                obligation_ids=[obligation.id],
            ),
        )

    assert database.get_review(review.id).revision == 1
    assert [event.action for event in database.list_events(review.id)] == ["create_review"]


def test_expired_finding_waiver_reopens_the_admission_blocker(tmp_path: Path):
    repo, base, target = create_billing_repo(tmp_path)
    database = Database(tmp_path / "expired-finding-waiver.db")
    service = ReviewService(database)
    project = service.create_project(
        name="Expiring finding waiver",
        repo_path=repo,
        head_ref=base,
        test_command=["python3", "-m", "unittest", "-q"],
        claims=[
            StructuralClaim(
                id="billing.no_new_legacy_reads",
                title="No new legacy billing reads",
                forbidden_modules=["legacy.billing"],
            )
        ],
    )
    review = service.create_review(project.id, base_ref=base, target_ref=target)
    waived = service.decide(
        review.id,
        DecisionAction(
            action="waive",
            actor="billing-lead",
            reason="Temporary bridge while the replacement endpoint stabilizes",
            scope="checkout.total",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            finding_ids=[review.findings[0].id],
        ),
    )
    waived.waivers[-1].expires_at = datetime.now(UTC) - timedelta(seconds=1)
    database.save_review(waived)

    manifest = service.get_change_package(review.id)
    critical = next(item for item in manifest.admission_checks if item.key == "critical_findings")
    assert critical.status == "block"
    with pytest.raises(DecisionBlocked, match="critical"):
        service.decide(review.id, DecisionAction(action="commit", actor="billing-lead"))

    renewed = service.decide(
        review.id,
        DecisionAction(
            action="waive",
            actor="billing-lead",
            reason="Renewed exception after reviewing the still bounded migration risk",
            scope="checkout.total",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            finding_ids=[review.findings[0].id],
        ),
    )
    assert len(renewed.waivers) == 2
    renewed_check = next(
        item
        for item in service.get_change_package(review.id).admission_checks
        if item.key == "critical_findings"
    )
    assert renewed_check.status == "pass"
