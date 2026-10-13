from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from system.domain.models import AuditEvent, StructuralClaim
from system.services.ai_copilot import ConsensusCopilot, CritiqueDraft, ReviewDraft, coerce_draft_payload
from system.services.ai_copilot import (
    CRITIQUE_SCHEMA,
    INTENT_SCHEMA,
    REVIEW_SCHEMA,
    SYNTHESIS_SCHEMA,
)
from system.services.database import BackupValidationError, ConcurrentTransitionError, Database
from system.services.llm import EvidenceSummarizer, LLMConfig, ModelGeneration
from system.services.review_service import ReviewService
from system.web.app import create_app
from tests.helpers import create_billing_repo


def _review_fixture(tmp_path: Path):
    repo, base, target = create_billing_repo(tmp_path)
    database = Database(tmp_path / "ai-copilot.db")
    reviews = ReviewService(database)
    project = reviews.create_project(
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
                evidence_obligations=["source policy passed on the target revision"],
            )
        ],
    )
    review = reviews.create_review(project.id, base_ref=base, target_ref=target)
    return database, reviews, project, review


def _disabled_gateway() -> EvidenceSummarizer:
    return EvidenceSummarizer(LLMConfig(enabled=False))


def test_copilot_schemas_forbid_extra_properties_for_openai_strict_mode():
    def object_schemas(value):
        if isinstance(value, dict):
            if value.get("type") == "object":
                yield value
            for child in value.values():
                yield from object_schemas(child)
        elif isinstance(value, list):
            for child in value:
                yield from object_schemas(child)

    for schema in (REVIEW_SCHEMA, CRITIQUE_SCHEMA, SYNTHESIS_SCHEMA, INTENT_SCHEMA):
        objects = list(object_schemas(schema))
        assert objects
        assert all(item.get("additionalProperties") is False for item in objects)


def test_review_copilot_fallback_is_grounded_persisted_and_advisory(tmp_path: Path):
    database, reviews, _project, review = _review_fixture(tmp_path)
    copilot = ConsensusCopilot(database, reviews, _disabled_gateway())

    before_events = database.list_events(review.id)
    run = copilot.ask_review(
        review.id,
        question="Why is this change blocked?",
        actor="lead",
        deliberate=False,
    )

    assert run.feature == "review_copilot"
    assert run.source == "deterministic"
    assert run.grounded is True
    assert run.citations
    assert run.citation_precision == 1
    assert "cannot approve" in run.result["boundary"].lower()
    assert database.get_ai_run(run.id).id == run.id
    assert database.list_events(review.id) == before_events


def test_evidence_gap_planner_finds_missing_obligations_and_records_checks(
    tmp_path: Path,
    monkeypatch,
):
    database, reviews, _project, review = _review_fixture(tmp_path)
    copilot = ConsensusCopilot(database, reviews, _disabled_gateway())

    def unexpected_diff(*_args, **_kwargs):
        raise AssertionError("gap planning must not compute a repository diff")

    monkeypatch.setattr(reviews, "get_diff", unexpected_diff)

    run = copilot.plan_evidence_gaps(review.id, actor="lead")

    gaps = run.result["gaps"]
    assert any(item["kind"] == "missing_obligation" for item in gaps)
    assert all(item["suggested_check"] for item in gaps)
    valid_ids = {
        item.id
        for item in copilot.build_review_context(review.id, include_diff=False).cards
    }
    assert {citation.id for citation in run.citations} <= valid_ids


class QueueGateway:
    def __init__(self, payloads: list[dict]):
        self.payloads = list(payloads)
        self.config = LLMConfig(
            enabled=True,
            provider="openai_chat_completions_compatible",
            api_key="test-key",
            model="critic-test",
        )
        self.calls: list[str] = []

    def generate_json(self, *, system_prompt, data, schema, schema_name, schema_description):
        del data, schema, schema_description
        self.calls.append(schema_name)
        return ModelGeneration(
            payload=self.payloads.pop(0),
            source="model",
            provider=self.config.provider,
            model=self.config.model,
            latency_ms=7,
            usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        )


def test_deliberate_copilot_uses_proposer_critic_and_synthesizer(tmp_path: Path):
    database, reviews, _project, review = _review_fixture(tmp_path)
    catalog = ConsensusCopilot(database, reviews, _disabled_gateway()).build_review_context(review.id)
    finding_id = next(card.id for card in catalog.cards if card.kind == "finding")
    gateway = QueueGateway(
        [
            {
                "answer": "The change is blocked by a critical dependency finding.",
                "citation_ids": [finding_id],
                "uncertainties": [],
                "suggested_checks": ["Replace the forbidden import and rerun tests."],
            },
            {
                "supported_claims": ["A critical finding is open."],
                "unsupported_claims": [],
                "disagreements": ["Passing tests do not resolve policy evidence."],
                "citation_ids": [finding_id],
            },
            {
                "answer": "The open critical finding blocks admission even though tests pass.",
                "citation_ids": [finding_id],
                "uncertainties": ["No replacement implementation is present."],
                "suggested_checks": ["Replace the import and rerun the governed checks."],
                "disagreements": ["Test success is insufficient for policy admission."],
            },
        ]
    )
    copilot = ConsensusCopilot(database, reviews, gateway)

    run = copilot.ask_review(
        review.id,
        question="Can this be committed?",
        actor="lead",
        deliberate=True,
    )

    assert gateway.calls == ["review_proposal", "review_critique", "review_synthesis"]
    assert run.source == "model"
    assert run.grounded is False
    assert run.faithfulness_score == 0
    assert "semantic_support_unverified" in run.quality_flags
    assert run.result["disagreements"]
    assert run.usage["total_tokens"] == 45
    assert run.citations[0].id == finding_id


def test_copilot_discards_an_answer_when_review_evidence_changes_midflight(
    tmp_path: Path,
    monkeypatch,
):
    database, reviews, _project, review = _review_fixture(tmp_path)
    catalog = ConsensusCopilot(database, reviews, _disabled_gateway()).build_review_context(
        review.id
    )
    finding_id = next(card.id for card in catalog.cards if card.kind == "finding")
    gateway = QueueGateway(
        [
            {
                "answer": "The cited finding blocks this review.",
                "citation_ids": [finding_id],
                "uncertainties": [],
                "suggested_checks": ["Resolve the finding."],
            }
        ]
    )
    generate = gateway.generate_json

    def generate_then_advance_review(**kwargs):
        result = generate(**kwargs)
        current = database.get_review(review.id)
        next_review = current.model_copy(
            update={
                "revision": current.revision + 1,
                "updated_at": datetime.now(UTC),
            }
        )
        database.apply_review_transition(
            review=next_review,
            event=AuditEvent(
                review_id=review.id,
                action="summarize",
                actor="system",
            ),
            expected_review_revision=current.revision,
        )
        return result

    monkeypatch.setattr(gateway, "generate_json", generate_then_advance_review)
    copilot = ConsensusCopilot(database, reviews, gateway)

    with pytest.raises(ConcurrentTransitionError, match="evidence changed"):
        copilot.ask_review(
            review.id,
            question="Can this be committed?",
            actor="lead",
            deliberate=False,
        )

    assert database.list_ai_runs(review_id=review.id) == []


def test_unknown_model_citations_are_rejected_with_a_safe_fallback(tmp_path: Path):
    database, reviews, _project, review = _review_fixture(tmp_path)
    gateway = QueueGateway(
        [
            {
                "answer": "Invented external approval exists.",
                "citation_ids": ["evidence:not-real"],
                "uncertainties": [],
                "suggested_checks": [],
            }
        ]
    )
    copilot = ConsensusCopilot(database, reviews, gateway)

    run = copilot.ask_review(review.id, question="Is there approval?", actor="lead", deliberate=False)

    assert run.source == "deterministic"
    assert "unknown_citation_rejected" in run.quality_flags
    assert all(item.id != "evidence:not-real" for item in run.citations)
    assert "Invented external approval" not in run.result["answer"]


def test_incomplete_deliberation_does_not_masquerade_as_a_synthesis(tmp_path: Path):
    database, reviews, _project, review = _review_fixture(tmp_path)
    catalog = ConsensusCopilot(database, reviews, _disabled_gateway()).build_review_context(review.id)
    finding_id = next(card.id for card in catalog.cards if card.kind == "finding")
    gateway = QueueGateway(
        [
            {
                "answer": "A proposal exists.",
                "citation_ids": [finding_id],
                "uncertainties": [],
                "suggested_checks": ["Verify the finding."],
            },
            {"not": "a valid critique"},
        ]
    )
    copilot = ConsensusCopilot(database, reviews, gateway)

    run = copilot.ask_review(review.id, question="Can this ship?", actor="lead", deliberate=True)

    assert gateway.calls == ["review_proposal", "review_critique"]
    assert run.source == "deterministic"
    assert "critique_validation_failed" in run.quality_flags
    assert run.result["proposal"] is None


def test_ai_api_interprets_intent_without_creating_it_and_tracks_feedback(tmp_path: Path):
    repo, base, _target = create_billing_repo(tmp_path)
    app = create_app(tmp_path / "ai-api.db", require_authentication=False)
    app.state.copilot.gateway = _disabled_gateway()
    with TestClient(app) as client:
        project = client.post(
            "/api/projects",
            json={
                "name": "Billing",
                "repo_path": str(repo),
                "head_ref": base,
                "test_command": [],
                "claims": [],
            },
        ).json()

        response = client.post(
            f"/api/projects/{project['id']}/ai/interpret-intent",
            json={
                "request": "Remove the legacy billing import without changing rate semantics in checkout.py",
                "context": "Prefer a compatibility path and surface semantic uncertainty.",
                "base_ref": base,
            },
        )

        assert response.status_code == 200
        run = response.json()
        assert run["feature"] == "intent_interpreter"
        assert len(run["result"]["candidates"]) >= 2
        assert run["result"]["clarification_questions"]
        assert client.get(f"/api/projects/{project['id']}/intents").json() == []

        feedback = client.post(
            f"/api/ai/runs/{run['id']}/feedback",
            json={
                "verdict": "edited",
                "note": "Kept candidate A and clarified rate semantics.",
                "edited_response": "Use the compatibility candidate while semantics remain uncertain.",
            },
        )
        assert feedback.status_code == 200
        assert feedback.json()["feedback"]["verdict"] == "edited"

        invalid_feedback = client.post(
            f"/api/ai/runs/{run['id']}/feedback",
            json={"verdict": "edited", "note": "Missing the edited answer."},
        )
        assert invalid_feedback.status_code == 422

        metrics = client.get(f"/api/projects/{project['id']}/ai/evals")
        assert metrics.status_code == 200
        assert metrics.json()["runs"] == 1
        assert metrics.json()["feedback"]["edited"] == 1


def test_verified_backup_preserves_ai_run_and_feedback_links(tmp_path: Path):
    database, reviews, _project, review = _review_fixture(tmp_path)
    copilot = ConsensusCopilot(database, reviews, _disabled_gateway())
    run = copilot.ask_review(
        review.id,
        question="What is blocked?",
        actor="lead",
        deliberate=False,
    )
    copilot.record_feedback(
        run.id,
        verdict="accepted",
        actor="lead",
        note="The citations match the control record.",
    )
    backup_path = tmp_path / "backup" / "with-ai.db"

    report = database.backup(backup_path)
    restored = Database(backup_path)

    assert report["health"]["ai_runs"] == 1
    assert report["health"]["ai_feedback"] == 1
    restored_run = restored.get_ai_run(run.id)
    assert restored_run.review_id == review.id
    assert restored_run.feedback is not None
    assert restored_run.feedback.verdict == "accepted"


def test_snapshot_validation_rejects_a_mismatched_ai_run_row(tmp_path: Path):
    database, reviews, _project, review = _review_fixture(tmp_path)
    run = ConsensusCopilot(database, reviews, _disabled_gateway()).ask_review(
        review.id,
        question="What is blocked?",
        actor="lead",
        deliberate=False,
    )
    with database.connect() as connection:
        connection.execute(
            "UPDATE ai_runs SET feature = ? WHERE id = ?",
            ("intent_interpreter", run.id),
        )

    with pytest.raises(
        BackupValidationError,
        match="missing or mismatched control object",
    ):
        Database.validate_snapshot(database.path)


def test_snapshot_validation_rejects_feedback_embedded_in_an_ai_run(tmp_path: Path):
    database, reviews, _project, review = _review_fixture(tmp_path)
    copilot = ConsensusCopilot(database, reviews, _disabled_gateway())
    run = copilot.ask_review(
        review.id,
        question="What is blocked?",
        actor="lead",
        deliberate=False,
    )
    run_with_feedback = copilot.record_feedback(
        run.id,
        verdict="accepted",
        actor="lead",
    )
    with database.connect() as connection:
        connection.execute(
            "UPDATE ai_runs SET body = ? WHERE id = ?",
            (run_with_feedback.model_dump_json(), run.id),
        )

    with pytest.raises(
        BackupValidationError,
        match="missing or mismatched control object",
    ):
        Database.validate_snapshot(database.path)


def test_feedback_actor_cannot_normalize_to_an_empty_identity(tmp_path: Path):
    database, reviews, _project, review = _review_fixture(tmp_path)
    run = ConsensusCopilot(database, reviews, _disabled_gateway()).ask_review(
        review.id,
        question="What is blocked?",
        actor="lead",
        deliberate=False,
    )

    with pytest.raises(ValueError, match="actor"):
        ConsensusCopilot(database, reviews, _disabled_gateway()).record_feedback(
            run.id,
            verdict="accepted",
            actor="   ",
        )


def test_snapshot_validation_rejects_an_ai_run_linked_to_another_project_review(
    tmp_path: Path,
):
    database, reviews, _project, review = _review_fixture(tmp_path)
    run = ConsensusCopilot(database, reviews, _disabled_gateway()).ask_review(
        review.id,
        question="What is blocked?",
        actor="lead",
        deliberate=False,
    )
    other_root = tmp_path / "other"
    other_root.mkdir()
    other_repo, other_base, other_target = create_billing_repo(other_root)
    other_project = reviews.create_project(
        name="Other project",
        repo_path=other_repo,
        head_ref=other_base,
        test_command=[],
        claims=[],
    )
    other_review = reviews.create_review(
        other_project.id,
        base_ref=other_base,
        target_ref=other_target,
    )
    mismatched_run = run.model_copy(update={"review_id": other_review.id})
    with pytest.raises(ValueError, match="must belong to the same project"):
        database.save_ai_run(
            mismatched_run.model_copy(update={"id": "ai-run-cross-project"})
        )
    with database.connect() as connection:
        connection.execute(
            "UPDATE ai_runs SET review_id = ?, body = ? WHERE id = ?",
            (other_review.id, mismatched_run.model_dump_json(), run.id),
        )

    with pytest.raises(
        BackupValidationError,
        match="missing or mismatched control object",
    ):
        Database.validate_snapshot(database.path)


class UnavailableGateway(QueueGateway):
    def generate_json(self, *, system_prompt, data, schema, schema_name, schema_description):
        del system_prompt, data, schema, schema_description
        self.calls.append(schema_name)
        return ModelGeneration(
            source="deterministic",
            provider="local_rules",
            latency_ms=31000,
            fallback_reason="JSONDecodeError: structured model output unavailable",
        )


def test_gateway_fallback_is_reported_as_model_unavailable_not_as_validation_failure(tmp_path: Path):
    database, reviews, _project, review = _review_fixture(tmp_path)
    copilot = ConsensusCopilot(database, reviews, UnavailableGateway([]))

    run = copilot.ask_review(review.id, question="What blocks approval?", actor="lead", deliberate=True)

    assert run.source == "deterministic"
    assert "model_unavailable" in run.quality_flags
    assert "proposal_validation_failed" not in run.quality_flags
    assert run.result["answer"]
    assert run.citations


def test_provider_payload_shaping_keeps_citations_and_drops_noise():
    shaped = coerce_draft_payload(
        {
            "answer": "Blocked by one finding.",
            "citation_ids": [{"id": "finding:abc"}, "evidence:def", ""],
            "uncertainties": {"note": "runtime trace is stale"},
            "suggested_checks": None,
            "confidence": 0.9,
            "reasoning": "should be dropped",
        },
        ReviewDraft,
    )
    draft = ReviewDraft.model_validate(shaped)
    assert draft.citation_ids == ["finding:abc", "evidence:def"]
    assert draft.uncertainties == ['{"note": "runtime trace is stale"}']
    assert draft.suggested_checks == []
    assert "reasoning" not in shaped and "confidence" not in shaped


def test_verbose_critique_payload_is_shaped_instead_of_failing(tmp_path: Path):
    database, reviews, _project, review = _review_fixture(tmp_path)
    catalog = ConsensusCopilot(database, reviews, _disabled_gateway()).build_review_context(review.id)
    finding_id = next(card.id for card in catalog.cards if card.kind == "finding")
    gateway = QueueGateway(
        [
            {"answer": "A proposal exists.", "citation_ids": [finding_id], "uncertainties": [], "suggested_checks": []},
            {
                "supported_claims": [{"claim": "The finding is open", "card": finding_id}],
                "unsupported_claims": [],
                "disagreements": [],
                "citation_ids": [finding_id],
                "verdict": "extra key from a verbose provider",
            },
            {"answer": "Synthesis.", "citation_ids": [finding_id], "uncertainties": [], "suggested_checks": [], "disagreements": []},
        ]
    )
    copilot = ConsensusCopilot(database, reviews, gateway)

    run = copilot.ask_review(review.id, question="Can this ship?", actor="lead", deliberate=True)

    assert gateway.calls == ["review_proposal", "review_critique", "review_synthesis"]
    assert run.source == "model"
    assert "critique_validation_failed" not in run.quality_flags
    assert CritiqueDraft.model_validate(run.result["critique"]).supported_claims == [f"The finding is open"]
