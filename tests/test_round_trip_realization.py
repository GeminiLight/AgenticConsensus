from datetime import UTC, datetime
from pathlib import Path

import pytest

from system.domain.transitions import DecisionBlocked
from system.domain.models import StructuralClaim
from system.services.database import Database
from system.services.git_service import GitError, GitRepository
from system.services.review_service import ReviewService

from .helpers import commit, run


def _create_round_trip_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "round-trip-repo"
    repo.mkdir()
    run(repo, "git", "init", "-q")
    run(repo, "git", "config", "user.email", "test@example.test")
    run(repo, "git", "config", "user.name", "Test")
    for package in ("legacy", "billing"):
        (repo / package).mkdir()
        (repo / package / "__init__.py").write_text("", encoding="utf-8")
    (repo / "legacy" / "billing.py").write_text("RATE = 2\n", encoding="utf-8")
    (repo / "billing" / "pricing.py").write_text("RATE = 2\n", encoding="utf-8")
    (repo / "billing" / "compat.py").write_text("RATE = 2\n", encoding="utf-8")
    (repo / "checkout.py").write_text(
        "from legacy.billing import RATE\n\n\ndef total(value):\n    return value * RATE\n",
        encoding="utf-8",
    )
    (repo / "test_checkout.py").write_text(
        "import unittest\nfrom checkout import total\n\n"
        "class CheckoutTest(unittest.TestCase):\n"
        "    def test_total(self):\n"
        "        self.assertEqual(total(3), 6)\n",
        encoding="utf-8",
    )
    return repo, commit(repo, "base with legacy pricing import")


def _selected_intent(tmp_path: Path, *, from_module: str = "legacy.billing"):
    repo, base = _create_round_trip_repo(tmp_path)
    database = Database(tmp_path / "round-trip.db")
    service = ReviewService(database)
    project = service.create_project(
        name="Pricing migration",
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
    candidates = [
        {
            "title": "Use pricing v2",
            "summary": "Replace the legacy import with billing.pricing.",
            "structural_delta": {
                "kind": "python_import_substitution",
                "path": "checkout.py",
                "from_module": from_module,
                "to_module": "billing.pricing",
            },
            "uncertainties": ["Confirm RATE compatibility"],
            "provenance": "agent/pricing-v2",
        },
        {
            "title": "Use compatibility adapter",
            "summary": "Replace the legacy import with billing.compat.",
            "structural_delta": {
                "kind": "python_import_substitution",
                "path": "checkout.py",
                "from_module": from_module,
                "to_module": "billing.compat",
            },
            "uncertainties": ["Confirm migration expiry"],
            "provenance": "agent/compat",
        },
    ]
    intent = service.create_intent(
        project.id,
        request="Remove the legacy billing dependency without changing RATE semantics.",
        context="Architecture review 17.",
        base_ref=base,
        created_by="architect@example.test",
        candidates=candidates,
    )
    chosen, rejected = intent.candidates
    intent = service.clarify_intent(
        intent.id,
        actor="billing-owner@example.test",
        question="Which module preserves RATE?",
        answer="Use billing.pricing.",
        retained_candidate_ids=[chosen.id],
        eliminated_candidate_ids=[rejected.id],
        resolved_uncertainties={chosen.id: chosen.uncertainties},
        expected_revision=1,
    )
    intent = service.select_intent_candidate(
        intent.id,
        candidate_id=chosen.id,
        actor="architecture-owner@example.test",
        reason="The owner confirmed the pricing contract.",
        expected_revision=2,
    )
    return database, service, project, intent, repo, base


def test_phi_creates_isolated_git_diff_then_psi_rehydrates_zero_discrepancy(tmp_path: Path):
    database, service, _, intent, repo_path, base = _selected_intent(tmp_path)
    realizer = getattr(service, "realize_intent", None)
    assert callable(realizer), "ReviewService must expose the bounded Phi operator"
    original_head = run(repo_path, "git", "rev-parse", "HEAD")
    original_status = run(repo_path, "git", "status", "--short")

    realized = realizer(
        intent.id,
        actor="builder-agent@example.test",
        expected_revision=3,
    )

    assert realized.status == "realized"
    assert realized.revision == 4
    assert realized.realized_review_id
    record = realized.realization_attempts[-1]
    assert record.status == "succeeded"
    assert record.failed_preconditions == []
    assert record.target_ref
    assert GitRepository(repo_path).resolve(record.git_ref) == record.target_ref
    assert "-from legacy.billing import RATE" in record.artifact_diff
    assert "+from billing.pricing import RATE" in record.artifact_diff
    assert record.rehydrated_candidates[0].structural_delta == record.predicted_delta
    assert record.selected_rehydration_id == record.rehydrated_candidates[0].id
    assert record.round_trip_discrepancy == 0
    assert record.observable_coverage == 1

    review = database.get_review(realized.realized_review_id)
    assert review.intent_id == intent.id
    assert review.selected_interpretation_id == intent.selected_candidate_id
    assert review.realization_id == record.id
    assert review.base_ref == base
    assert review.target_ref == record.target_ref
    assert review.round_trip_discrepancy == 0
    assert review.observable_coverage == 1
    assert run(repo_path, "git", "rev-parse", "HEAD") == original_head
    assert run(repo_path, "git", "status", "--short") == original_status == ""


def test_phi_records_failed_preconditions_without_mutating_repository(tmp_path: Path):
    database, service, _, intent, repo_path, _ = _selected_intent(
        tmp_path, from_module="legacy.missing"
    )
    assert callable(getattr(service, "realize_intent", None)), "Phi is not implemented"
    original_head = run(repo_path, "git", "rev-parse", "HEAD")

    attempted = service.realize_intent(
        intent.id,
        actor="builder-agent@example.test",
        expected_revision=3,
    )

    assert attempted.status == "selected"
    assert attempted.realized_review_id is None
    assert attempted.revision == 4
    record = attempted.realization_attempts[-1]
    assert record.status == "failed"
    assert any("source import" in item for item in record.failed_preconditions)
    assert record.target_ref is None
    assert database.list_reviews() == []
    assert run(repo_path, "git", "rev-parse", "HEAD") == original_head
    assert run(repo_path, "git", "status", "--short") == ""


def test_phi_removes_its_proposal_ref_when_diff_capture_fails(
    tmp_path: Path,
    monkeypatch,
):
    repo, base = _create_round_trip_repo(tmp_path)
    repository = GitRepository(repo)

    def fail_diff(*_args, **_kwargs):
        raise GitError("simulated diff failure")

    monkeypatch.setattr(repository, "diff", fail_diff)
    result = repository.realize_python_import_substitution(
        base,
        path="checkout.py",
        from_module="legacy.billing",
        to_module="billing.pricing",
        proposal_id="diff-failure",
    )

    assert result.target_ref is None
    assert result.git_ref is None
    assert any("simulated diff failure" in item for item in result.failed_preconditions)
    assert run(
        repo,
        "git",
        "for-each-ref",
        "--format=%(refname)",
        "refs/agentic-consensus/proposals/diff-failure",
    ) == ""


def test_realization_removes_its_proposal_ref_when_rehydration_raises(
    tmp_path: Path,
    monkeypatch,
):
    database, service, _, intent, repo_path, _ = _selected_intent(tmp_path)

    def fail_rehydration(*_args, **_kwargs):
        raise RuntimeError("simulated rehydration failure")

    monkeypatch.setattr(
        "system.services.review_service.rehydrate_python_import_substitutions",
        fail_rehydration,
    )

    with pytest.raises(RuntimeError, match="simulated rehydration failure"):
        service.realize_intent(
            intent.id,
            actor="builder-agent@example.test",
            expected_revision=intent.revision,
        )

    assert database.get_intent(intent.id).revision == intent.revision
    assert database.list_reviews(intent.project_id) == []
    assert run(
        repo_path,
        "git",
        "for-each-ref",
        "--format=%(refname)",
        f"refs/agentic-consensus/proposals/{intent.id}",
    ) == ""


def test_concurrent_intent_change_during_phi_leaves_no_orphan_review_or_ref(
    tmp_path: Path, monkeypatch
):
    database, service, _, intent, repo_path, _ = _selected_intent(tmp_path)
    original_realize = GitRepository.realize_python_import_substitution

    def realize_then_advance_intent(repository, *args, **kwargs):
        artifact = original_realize(repository, *args, **kwargs)
        competing = database.get_intent(intent.id)
        competing.revision += 1
        competing.updated_at = datetime.now(UTC)
        database.apply_intent_transition(
            competing, expected_revision=intent.revision
        )
        return artifact

    monkeypatch.setattr(
        GitRepository,
        "realize_python_import_substitution",
        realize_then_advance_intent,
    )

    with pytest.raises(DecisionBlocked, match="stale intent state"):
        service.realize_intent(
            intent.id,
            actor="builder-agent@example.test",
            expected_revision=intent.revision,
        )

    assert database.list_reviews(intent.project_id) == []
    assert database.list_events("missing-review") == []
    proposal_refs = run(
        repo_path,
        "git",
        "for-each-ref",
        "--format=%(refname)",
        f"refs/agentic-consensus/proposals/{intent.id}",
    )
    assert proposal_refs == ""


def test_contract_graph_links_intent_selection_phi_psi_and_review(tmp_path: Path):
    _, service, _, intent, _, _ = _selected_intent(tmp_path)
    realized = service.realize_intent(
        intent.id,
        actor="builder-agent@example.test",
        expected_revision=3,
    )

    graph = service.get_contract_graph(realized.realized_review_id)

    node_types = {node.type for node in graph.nodes}
    assert {"intent", "interpretation", "realization", "rehydration"}.issubset(node_types)
    relations = {(edge.source, edge.target, edge.relation) for edge in graph.edges}
    record = realized.realization_attempts[-1]
    assert (f"intent:{intent.id}", f"interpretation:{intent.selected_candidate_id}", "selects") in relations
    assert (
        f"interpretation:{intent.selected_candidate_id}",
        f"realization:{record.id}",
        "realizes",
    ) in relations
    assert (
        f"realization:{record.id}",
        f"rehydration:{record.selected_rehydration_id}",
        "rehydrates",
    ) in relations
    assert (
        f"rehydration:{record.selected_rehydration_id}",
        "state:proposal",
        "round_trip_matches",
    ) in relations
