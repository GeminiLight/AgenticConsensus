from pathlib import Path
import json

from system.demo import seed_demo
from system.services.database import Database
from system.services.review_service import ReviewService


def test_seeded_demo_is_a_complete_decision_scenario(tmp_path: Path):
    database_path = tmp_path / "control.db"
    result = seed_demo(database_path, tmp_path / "demo-repo", reset=False)
    database = Database(database_path)
    project = database.get_project(result.project_id)
    review = database.get_review(result.review_id)

    assert project.head_ref == review.base_ref
    assert project.version == 42
    assert project.repo_label == "demo://task-scoped-capability-migration"
    assert project.claims[0].id == "authority.task_scoped_only"
    assert project.claims[0].introduced_version == 37
    assert project.policy_id == "security-change-control/v1"
    assert project.default_authority == "security owner"
    assert project.authority_grants[0].actors == ["security-lead@example.test"]
    assert "attest" in project.authority_grants[0].actions
    assert "manage_trust" in project.authority_grants[0].actions
    assert project.attestation_trust_roots[0].algorithm == "ed25519"
    assert project.attestation_trust_roots[0].verifier_id == "https://agentic-consensus.local/demo-verifier/v1"
    assert len(review.evidence_obligations) == 2
    assert all(item.claim_id == "authority.task_scoped_only" for item in review.evidence_obligations)
    assert review.evidence_obligations[0].verification == "dsse_ed25519"
    assert review.evidence_obligations[0].required_verified_level == "CONSENSUS_CLAIM_POLICY_V1"
    assert result.attestation_path is not None
    assert result.attestation_path.is_file()
    envelope = json.loads(result.attestation_path.read_text(encoding="utf-8"))
    assert envelope["payloadType"] == "application/vnd.in-toto+json"
    manifest = ReviewService(database).get_change_package(review.id)
    assert [item.status for item in manifest.obligation_statuses] == ["missing", "missing"]
    updated = ReviewService(database).attach_dsse_attestation(
        review.id,
        obligation_ids=[review.evidence_obligations[0].id],
        envelope=envelope,
    )
    manifest = ReviewService(database).get_change_package(updated.id)
    assert [item.status for item in manifest.obligation_statuses] == ["satisfied", "missing"]
    assert next(item for item in review.evidence if item.kind == "tests").status == "pass"
    assert any(item.kind == "unobservable" for item in review.findings)
    assert any(item.kind == "policy" and item.freshness == "stale" for item in review.evidence)
    assert review.intent_summary == "Add an archive connector without widening credential authority"
    intents = database.list_intents(project.id)
    assert len(intents) == 1
    assert intents[0].status == "realized"
    assert len(intents[0].candidates) == 2
    assert intents[0].clarification_history
    realization = intents[0].realization_attempts[-1]
    assert realization.status == "succeeded"
    assert realization.round_trip_discrepancy == 0
    assert realization.observable_coverage == 1
    assert realization.git_ref.startswith("refs/agentic-consensus/proposals/")
    linked_review = database.get_review(intents[0].realized_review_id)
    assert linked_review.intent_id == intents[0].id
    assert linked_review.realization_id == realization.id
    assert (tmp_path / "demo-repo" / ".agentic-consensus-demo").exists()
