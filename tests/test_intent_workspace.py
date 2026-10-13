from pathlib import Path

import pytest

from system.domain.models import StructuralClaim
from system.services.database import Database
from system.services.review_service import DecisionBlocked, ReviewService

from .helpers import create_billing_repo


def _service_with_project(tmp_path: Path):
    repo, base, _ = create_billing_repo(tmp_path)
    database = Database(tmp_path / "consensus.db")
    service = ReviewService(database)
    project = service.create_project(
        name="Billing migration",
        repo_path=repo,
        head_ref=base,
        test_command=["python3", "-m", "unittest", "-q"],
        claims=[
            StructuralClaim(
                id="billing.no_legacy_import",
                title="Checkout does not depend on legacy billing",
                forbidden_modules=["legacy.billing"],
                authority="architecture owner",
            )
        ],
    )
    return database, service, project, base


def _candidates():
    return [
        {
            "title": "Move checkout to pricing v2",
            "summary": "Replace the legacy billing import with billing.pricing.",
            "structural_delta": {
                "kind": "python_import_substitution",
                "path": "checkout.py",
                "from_module": "legacy.billing",
                "to_module": "billing.pricing",
            },
            "uncertainties": ["Whether billing.pricing preserves RATE semantics"],
            "provenance": "coding-agent/candidate-a",
            "confidence": 0.72,
        },
        {
            "title": "Move checkout to negotiated pricing",
            "summary": "Replace the legacy billing import with billing.negotiated.",
            "structural_delta": {
                "kind": "python_import_substitution",
                "path": "checkout.py",
                "from_module": "legacy.billing",
                "to_module": "billing.negotiated",
            },
            "uncertainties": ["Whether negotiated rates are permitted for every tenant"],
            "provenance": "coding-agent/candidate-b",
            "confidence": 0.51,
        },
    ]


def test_create_intent_preserves_language_request_candidates_and_base_version(tmp_path: Path):
    database, service, project, base = _service_with_project(tmp_path)
    creator = getattr(service, "create_intent", None)
    assert callable(creator), "ReviewService must expose the Intent Workspace"

    intent = creator(
        project.id,
        request="Remove the legacy billing dependency without changing rate semantics.",
        context="Checkout migration requested in architecture review 17.",
        base_ref=base,
        created_by="architect@example.test",
        candidates=_candidates(),
    )

    assert intent.project_id == project.id
    assert intent.base_ref == base
    assert intent.base_version == 1
    assert intent.revision == 1
    assert intent.status == "clarification_required"
    assert len(intent.candidates) == 2
    assert {candidate.provenance for candidate in intent.candidates} == {
        "coding-agent/candidate-a",
        "coding-agent/candidate-b",
    }
    assert database.get_intent(intent.id) == intent


def test_clarification_preserves_history_then_requires_explicit_selection(tmp_path: Path):
    database, service, project, base = _service_with_project(tmp_path)
    assert callable(getattr(service, "create_intent", None)), "Intent creation is not implemented"
    intent = service.create_intent(
        project.id,
        request="Remove the legacy billing dependency without changing rate semantics.",
        context="Checkout migration requested in architecture review 17.",
        base_ref=base,
        created_by="architect@example.test",
        candidates=_candidates(),
    )
    chosen, rejected = intent.candidates

    clarified = service.clarify_intent(
        intent.id,
        actor="billing-owner@example.test",
        question="Which pricing contract preserves the committed RATE semantics?",
        answer="Use billing.pricing; negotiated rates are outside this migration.",
        retained_candidate_ids=[chosen.id],
        eliminated_candidate_ids=[rejected.id],
        resolved_uncertainties={chosen.id: chosen.uncertainties},
        expected_revision=1,
    )

    assert clarified.revision == 2
    assert clarified.status == "ready_for_selection"
    assert clarified.selected_candidate_id is None
    assert clarified.candidates[0].status == "active"
    assert clarified.candidates[0].uncertainties == []
    assert clarified.candidates[1].status == "eliminated"
    assert clarified.clarification_history[0].actor == "billing-owner@example.test"
    assert clarified.clarification_history[0].before_candidate_ids == [chosen.id, rejected.id]
    assert clarified.clarification_history[0].after_candidate_ids == [chosen.id]

    selected = service.select_intent_candidate(
        intent.id,
        candidate_id=chosen.id,
        actor="architecture-owner@example.test",
        reason="The clarification confirms the committed rate contract.",
        expected_revision=2,
    )

    assert selected.revision == 3
    assert selected.status == "selected"
    assert selected.selected_candidate_id == chosen.id
    assert selected.selection_actor == "architecture-owner@example.test"
    assert selected.selection_reason.startswith("The clarification")
    assert database.get_intent(intent.id) == selected


def test_intent_transitions_reject_stale_revision_and_single_candidate_creation(tmp_path: Path):
    _, service, project, base = _service_with_project(tmp_path)
    assert callable(getattr(service, "create_intent", None)), "Intent creation is not implemented"
    with pytest.raises(ValueError, match="at least two"):
        service.create_intent(
            project.id,
            request="Move checkout to the new pricing module.",
            context="Architecture review 17.",
            base_ref=base,
            created_by="architect@example.test",
            candidates=_candidates()[:1],
        )

    intent = service.create_intent(
        project.id,
        request="Move checkout to a non-legacy pricing module.",
        context="Architecture review 17.",
        base_ref=base,
        created_by="architect@example.test",
        candidates=_candidates(),
    )
    with pytest.raises(DecisionBlocked, match="stale intent state"):
        service.clarify_intent(
            intent.id,
            actor="billing-owner@example.test",
            question="Which contract?",
            answer="Use billing.pricing.",
            retained_candidate_ids=[intent.candidates[0].id],
            eliminated_candidate_ids=[intent.candidates[1].id],
            resolved_uncertainties={},
            expected_revision=0,
        )


def test_clarification_can_revise_and_add_candidates_without_losing_prior_state(tmp_path: Path):
    _, service, project, base = _service_with_project(tmp_path)
    intent = service.create_intent(
        project.id,
        request="Choose a non-legacy pricing contract.",
        context="The architecture owner requested an explicit compatibility alternative.",
        base_ref=base,
        created_by="architect@example.test",
        candidates=_candidates(),
    )
    revised = intent.candidates[0].model_copy(deep=True)
    revised.summary = "Use the versioned pricing contract selected during clarification."
    revised.structural_delta.to_module = "billing.pricing_v2"
    revised.uncertainties = []
    revised.provenance = "clarification/revision-1"
    added = {
        "title": "Use the compatibility adapter",
        "summary": "Replace the legacy import with billing.compat.",
        "structural_delta": {
            "kind": "python_import_substitution",
            "path": "checkout.py",
            "from_module": "legacy.billing",
            "to_module": "billing.compat",
        },
        "uncertainties": ["Whether the adapter may remain after the migration window"],
        "provenance": "clarification/new-alternative",
        "confidence": 0.63,
    }

    clarified = service.clarify_intent(
        intent.id,
        actor="billing-owner@example.test",
        question="Should we include a bounded compatibility path?",
        answer="Keep negotiated pricing, revise the direct path to v2, and add an adapter option.",
        retained_candidate_ids=[candidate.id for candidate in intent.candidates],
        eliminated_candidate_ids=[],
        resolved_uncertainties={},
        candidate_revisions={revised.id: revised},
        added_candidates=[added],
        expected_revision=1,
    )

    record = clarified.clarification_history[0]
    assert record.revised_candidate_ids == [revised.id]
    assert len(record.added_candidate_ids) == 1
    assert record.before_candidates[0].structural_delta.to_module == "billing.pricing"
    assert record.after_candidates[0].structural_delta.to_module == "billing.pricing_v2"
    assert len(record.after_candidates) == 3
    assert len(clarified.candidates) == 3
    assert clarified.status == "clarification_required"


def test_intent_records_are_validated_in_backups_and_removed_with_the_project(tmp_path: Path):
    database, service, project, base = _service_with_project(tmp_path)
    intent = service.create_intent(
        project.id,
        request="Choose a non-legacy pricing contract.",
        context="Architecture review 17.",
        base_ref=base,
        created_by="architect@example.test",
        candidates=_candidates(),
    )
    backup_path = tmp_path / "intent-backup.db"

    report = database.backup(backup_path)

    assert report["health"]["intents"] == 1
    assert Database(backup_path, initialize=False).get_intent(intent.id) == intent
    database.delete_project_data(project.id)
    assert database.list_intents() == []
