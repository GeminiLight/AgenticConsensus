from pathlib import Path

from fastapi.testclient import TestClient

from system.domain.models import (
    ClaimDelta,
    DecisionRecord,
    Evidence,
    Finding,
    Project,
    ReviewPackage,
    StructuralClaim,
)
from system.services.database import Database
from system.services.review_service import ReviewService
from system.web.app import create_app
from tests.helpers import create_capability_repo


def graph_scenario(tmp_path: Path):
    repository, base_ref, target_ref = create_capability_repo(tmp_path)
    database = Database(tmp_path / "contract-graph.db")
    project = Project(
        name="Task-scoped capability migration",
        repo_path=str(repository),
        repo_label="demo://capability-migration",
        version=9,
        head_ref=target_ref,
        policy_id="security-change-control/v1",
        default_authority="security owner",
        authority_grants=[
            {
                "authority": "security owner",
                "actors": ["alice@example.test"],
                "actions": ["commit", "rollback", "attest", "manage_trust"],
            }
        ],
        claims=[
            StructuralClaim(
                id="authority.task_scoped_only",
                title="Connectors use only task-scoped capabilities",
                forbidden_modules=["legacy.workspace_credentials"],
                scope="connectors.*",
                introduced_version=7,
                authority="security owner",
            )
        ],
    )
    database.save_project(project)
    review = ReviewPackage(
        project_id=project.id,
        base_ref=base_ref,
        target_ref=target_ref,
        base_version=8,
        current_project_version=9,
        status="committed",
        intent_summary="Add an archive connector without widening authority",
        proposer="coding-agent/archive-connector",
        changed_paths=["connectors/archive.py"],
        claim_deltas=[
            ClaimDelta(
                claim_id="authority.task_scoped_only",
                operation="contest",
                status="unobservable",
                summary="The dynamic provider relation requires evidence",
                artifact_anchors=[
                    {
                        "path": "connectors/archive.py",
                        "kind": "code",
                        "relation": "observes",
                        "line": 5,
                        "version_ref": target_ref,
                    }
                ],
            )
        ],
        evidence=[
            Evidence(
                id="evidence-tests",
                kind="tests",
                status="pass",
                outcome="supports",
                summary="Target tests passed",
                claim_ids=["authority.task_scoped_only"],
                artifact_ref=target_ref,
                provenance="isolated_target_checkout",
            ),
            Evidence(
                id="evidence-policy",
                kind="policy",
                status="unknown",
                outcome="inconclusive",
                summary="Runtime credential provenance is not observed",
                claim_ids=["authority.task_scoped_only"],
                artifact_ref=target_ref,
                provenance="runtime_trace/missing",
            ),
        ],
        findings=[
            Finding(
                id="finding-dynamic-import",
                rule_id="authority.task_scoped_only",
                kind="unobservable",
                severity="critical",
                message="Dynamic import target cannot be resolved",
                path="connectors/archive.py",
                line=5,
                status="waived",
            )
        ],
        governing_policy="security-change-control/v1",
        required_authorities=["security owner"],
        decision_records=[
            DecisionRecord(
                id="decision-commit",
                action="commit",
                actor="alice@example.test",
                authority="security owner",
                policy_id="security-change-control/v1",
                reason="The admitted evidence and bounded exception satisfy policy",
                provenance="project_authority_grant",
            )
        ],
    )
    database.save_review(review)
    return database, project, review


def test_contract_graph_preserves_versioned_governance_relations(tmp_path: Path):
    database, project, review = graph_scenario(tmp_path)

    graph = ReviewService(database).get_contract_graph(review.id)

    assert graph.format == "agentic-consensus/contract-graph@0.1"
    assert graph.project_id == project.id
    assert graph.review_id == review.id
    assert graph.project_version == 9
    assert graph.review_status == "committed"
    assert {node.type for node in graph.nodes} >= {
        "base_state",
        "proposal",
        "current_state",
        "claim",
        "artifact",
        "evidence",
        "finding",
        "authority",
        "decision",
    }
    assert len({node.id for node in graph.nodes}) == len(graph.nodes)
    node_ids = {node.id for node in graph.nodes}
    assert all(edge.source in node_ids and edge.target in node_ids for edge in graph.edges)
    relations = {(edge.source, edge.target, edge.relation) for edge in graph.edges}
    assert ("state:base", "state:proposal", "proposes") in relations
    assert ("state:proposal", "artifact:connectors/archive.py", "changes") in relations
    assert (
        "artifact:connectors/archive.py",
        "claim:authority.task_scoped_only",
        "observes",
    ) in relations
    assert (
        "evidence:evidence-tests",
        "claim:authority.task_scoped_only",
        "supports",
    ) in relations
    assert (
        "finding:finding-dynamic-import",
        "claim:authority.task_scoped_only",
        "contests",
    ) in relations
    assert ("authority:security owner", "decision:decision-commit", "authorizes") in relations
    assert ("decision:decision-commit", "state:current", "commits") in relations
    assert ("state:current", "claim:authority.task_scoped_only", "governs") in relations
    decision = next(node for node in graph.nodes if node.id == "decision:decision-commit")
    assert decision.metadata["actor"] == "alice@example.test"
    assert decision.metadata["provenance"] == "project_authority_grant"
    assert str(repository_path := project.repo_path) not in graph.model_dump_json()
    assert repository_path


def test_contract_graph_api_and_local_visualization_assets_are_available(tmp_path: Path):
    database, _, review = graph_scenario(tmp_path)
    app = create_app(database.path, require_authentication=False)

    with TestClient(app) as client:
        response = client.get(f"/api/reviews/{review.id}/graph")
        assert response.status_code == 200
        assert response.json()["schema"] == "agentic-consensus/contract-graph@0.1"

        html = client.get("/").text
        assert 'src="/static/vendor/cytoscape-3.34.2.min.js"' in html
        assert 'id="contract-graph-panel"' in html
        assert 'id="contract-graph-canvas"' in html
        assert 'id="contract-graph-table"' in html
        assert 'id="contract-graph-detail"' in html
        assert 'id="contract-graph-fit"' in html
        assert 'id="contract-graph-expand"' in html
        assert 'id="contract-graph-export"' in html

        vendor = client.get("/static/vendor/cytoscape-3.34.2.min.js")
        assert vendor.status_code == 200
        assert "cytoscape" in vendor.text[:500].lower()
        assert client.get("/static/vendor/CYTOSCAPE-LICENSE.txt").status_code == 200

        javascript = client.get("/static/app.js").text
        stylesheet = client.get("/static/app.css").text
        assert "function renderContractGraph" in javascript
        assert "function downloadContractGraphSvg" in javascript
        assert "function toggleContractGraphFocus" in javascript
        assert "cytoscape({" in javascript
        assert "`/api/reviews/${reviewId}/graph`" in javascript
        assert ".contract-graph-shell" in stylesheet
        assert ".contract-graph-table" in stylesheet
        assert "https://unpkg.com" not in html + javascript
        assert "https://cdn.jsdelivr.net" not in html + javascript
        assert "wheelSensitivity" not in javascript
