from fastapi.testclient import TestClient
import pytest

from system.web.app import create_app
from tests.helpers import create_billing_repo, create_alternate_target


@pytest.fixture
def workspace(tmp_path):
    repo, base, target = create_billing_repo(tmp_path)
    with TestClient(create_app(tmp_path / "commitments.db", require_authentication=False)) as client:
        project = client.post("/api/projects", json={"name": "Checkout", "repo_path": str(repo),
            "head_ref": base, "test_command": ["python3", "-m", "unittest", "-q"], "claims": []}).json()
        review = client.post(f"/api/projects/{project['id']}/reviews", json={"base_ref": base, "target_ref": target}).json()
        yield client, project, review, repo


def proposal(review, **changes):
    return {"expected_revision": review["revision"], "actor": "lead", "request": "Keep checkout pricing compatible.",
        "reason": "Existing consumers must keep the same totals.", "title": "Stable checkout totals",
        "statement": "Checkout continues to return the same total for existing inputs.",
        "category": "compatibility", "paths": ["checkout.py"],
        "verification": "Compare totals against the prior release using representative inputs.", **changes}


def save(client, review, **changes):
    response = client.post(f"/api/reviews/{review['id']}/commitments", json=proposal(review, **changes))
    assert response.status_code == 200, response.text
    return response.json()


def verify(client, review):
    return client.post(f"/api/reviews/{review['id']}/evidence", json={"actor": "lead", "authority": "local operator",
        "policy_id": "local-single-user/v1", "obligation_ids": [review["commitment_changes"][0]["obligation_id"]],
        "summary": "Compared prior and target checkout totals on the recorded representative cases.",
        "provenance": "manual-comparison/record-1"})


def decide(client, review, action="commit"):
    return client.post(f"/api/reviews/{review['id']}/decisions", json={"action": action, "actor": "lead", "reason": "Reviewed the target-bound evidence and compatibility requirement."})


def test_proposal_is_persisted_but_not_authorized_or_verified(workspace):
    client, project, review, _ = workspace
    updated = save(client, review)
    change = updated["commitment_changes"][0]
    assert change["before"] is None
    assert change["after"]["statement"] == proposal(review)["statement"]
    assert change["recorded_by"] == "lead"
    assert updated["revision"] == review["revision"] + 1
    assert client.get("/api/projects").json()[0]["commitments"] == []
    assert client.get("/api/projects").json()[0]["version"] == project["version"]
    assert client.get(f"/api/reviews/{review['id']}").json()["commitment_changes"] == updated["commitment_changes"]
    denied = decide(client, updated)
    assert denied.status_code == 409 and "obligation" in denied.text
    events = client.get(f"/api/reviews/{review['id']}/events").json()
    assert events[-1]["action"] == "propose_commitment"
    assert events[-1]["payload"]["after"]["statement"] == change["after"]["statement"]


def test_long_verification_plan_survives_save_export_and_revision(workspace):
    client, _, review, repo = workspace
    plan = ("Check the exact public-field allowlist and exclude private values. " * 30)[:1990]
    assert 500 < len(plan) <= 2000
    updated = save(client, review, verification=plan)
    assert updated["commitment_changes"][0]["after"]["verification"] == plan
    assert updated["evidence_obligations"][0]["label"] == plan
    gaps = client.post(f"/api/reviews/{review['id']}/ai/evidence-gaps", json={"actor":"lead"})
    assert gaps.status_code == 200, gaps.text
    assert decide(client, updated).status_code == 409
    assert decide(client, updated, "rebase").status_code == 200
    current = client.get(f"/api/reviews/{review['id']}").json()
    target = create_alternate_target(repo, review["target_ref"], path="checkout.py", content="def total(value):\n    return value * 3\n", message="Revise implementation")
    followup = client.post(f"/api/reviews/{review['id']}/revisions", json={
        "expected_revision":current["revision"], "target_ref":target})
    assert followup.status_code == 201, followup.text
    exported = client.get(f"/api/reviews/{followup.json()['id']}/export").json()
    assert exported["review"]["evidence_obligations"][0]["label"] == plan
    assert exported["review"]["commitment_changes"][0]["after"]["verification"] == plan


def test_contract_graph_exposes_manual_commitment_and_artifact_link(workspace):
    client, _, review, _ = workspace
    updated = save(client, review)
    graph = client.get(f"/api/reviews/{review['id']}/graph").json()
    claim_id = updated["commitment_changes"][0]["after"]["id"]
    node = next((n for n in graph["nodes"] if n["id"] == f"claim:{claim_id}"), None)
    assert node is not None, "Manual commitments must be present in the same contract graph"
    assert node["status"] == "proposed"
    assert any(e["source"] == "artifact:checkout.py" and e["target"] == node["id"] for e in graph["edges"])


def test_approval_updates_project_and_rollback_restores_prior_state(workspace):
    client, project, review, _ = workspace
    updated = save(client, review)
    assert verify(client, updated).status_code == 200
    assert decide(client, updated).status_code == 200
    committed = client.get("/api/projects").json()[0]
    assert committed["commitments"] == [updated["commitment_changes"][0]["after"]]
    assert committed["version"] == project["version"] + 1
    assert decide(client, updated, "rollback").status_code == 200
    assert client.get("/api/projects").json()[0]["commitments"] == []
    assert client.get(f"/api/reviews/{review['id']}").json()["commitment_changes"] == updated["commitment_changes"]


def test_edit_invalidates_old_evidence_and_rejects_stale_writers(workspace):
    client, _, review, _ = workspace
    updated = save(client, review)
    assert verify(client, updated).status_code == 200
    current = client.get(f"/api/reviews/{review['id']}").json()
    change = current["commitment_changes"][0]
    stale = client.post(f"/api/reviews/{review['id']}/commitments", json=proposal(updated, commitment_id=change["after"]["id"]))
    assert stale.status_code == 409
    revised = save(client, current, commitment_id=change["after"]["id"], statement="Checkout preserves totals and rounding for existing inputs.")
    attestations = [item for item in revised["evidence"] if item["kind"] == "attestation"]
    assert attestations[0]["freshness"] == "stale"
    assert len(revised["commitment_changes"]) == 1
    assert decide(client, revised).status_code == 409
    assert verify(client, revised).status_code == 200
    assert decide(client, revised).status_code == 200


def test_next_change_keeps_baseline_and_requires_fresh_verification(workspace):
    client, project, review, repo = workspace
    first = save(client, review)
    assert verify(client, first).status_code == 200
    assert decide(client, first).status_code == 200
    target = create_alternate_target(repo, review["target_ref"], path="checkout.py", content="def total(value):\n    return value * 3\n", message="Change multiplier")
    later = client.post(f"/api/projects/{project['id']}/reviews", json={"base_ref": review["target_ref"], "target_ref": target}).json()
    assert later["commitment_baseline"] == [first["commitment_changes"][0]["after"]]
    assert any(item["claim_id"] == first["commitment_changes"][0]["after"]["id"] for item in later["evidence_obligations"])
    second = save(client, later, commitment_id=first["commitment_changes"][0]["after"]["id"], statement="Checkout uses the newly agreed multiplier of three.")
    assert second["commitment_changes"][0]["before"]["statement"] == first["commitment_changes"][0]["after"]["statement"]
    assert len(second["evidence_obligations"]) == 1


@pytest.mark.parametrize("changes", [{"paths": ["../secret"]}, {"paths": ["not-in-this-review.ts"]}, {"statement": " "}, {"commitment_id": "foreign-project-commitment"}])
def test_invalid_or_unbound_proposals_cannot_be_recorded(workspace, changes):
    client, _, review, _ = workspace
    response = client.post(f"/api/reviews/{review['id']}/commitments", json=proposal(review, **changes))
    assert response.status_code in {409, 422}
    assert client.get(f"/api/reviews/{review['id']}").json()["revision"] == review["revision"]


def test_rejected_review_does_not_change_project_and_cannot_be_edited(workspace):
    client, _, review, _ = workspace
    updated = save(client, review)
    assert decide(client, updated, "reject").status_code == 200
    assert client.get("/api/projects").json()[0]["commitments"] == []
    response = client.post(f"/api/reviews/{review['id']}/commitments", json=proposal(updated))
    assert response.status_code == 409


def test_an_old_waiver_cannot_authorize_a_revised_commitment(workspace):
    from datetime import UTC, datetime, timedelta
    client, _, review, _ = workspace
    updated = save(client, review)
    waived = client.post(f"/api/reviews/{review['id']}/decisions", json={"action": "waive", "actor": "lead",
        "reason": "Temporary exception for the original compatibility commitment.", "scope": "checkout.py",
        "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        "obligation_ids": [updated["commitment_changes"][0]["obligation_id"]]})
    assert waived.status_code == 200
    revised = save(client, waived.json(), commitment_id=updated["commitment_changes"][0]["after"]["id"], statement="Checkout may now change rounding semantics.")
    assert decide(client, revised).status_code == 409


def test_authenticated_proposal_cannot_impersonate_another_author(tmp_path):
    from tests.test_auth import bootstrap, csrf_headers
    repo, base, target = create_billing_repo(tmp_path)
    with TestClient(create_app(tmp_path / "identity.db")) as client:
        auth = bootstrap(client)
        headers = csrf_headers(auth)
        project = client.post("/api/projects", headers=headers, json={"name": "Identity", "repo_path": str(repo), "head_ref": base}).json()
        review = client.post(f"/api/projects/{project['id']}/reviews", headers=headers, json={"base_ref": base, "target_ref": target}).json()
        denied = client.post(f"/api/reviews/{review['id']}/commitments", headers=headers, json=proposal(review, actor="someone-else"))
        assert denied.status_code == 403
        saved = client.post(f"/api/reviews/{review['id']}/commitments", headers=headers, json=proposal(review, actor="alice@example.test"))
        assert saved.status_code == 200
        assert saved.json()["commitment_changes"][0]["recorded_by"] == "alice@example.test"


def reading(**changes):
    return {"path": "checkout.py", "start_line": 1, "end_line": 2,
            "label": "Checkout consumer", "summary": "The consumer imports the configured pricing implementation.",
            "relation": "context", **changes}


def test_source_readings_capture_real_target_lines_without_becoming_evidence(workspace):
    from system.services.git_service import GitRepository
    client, _, review, repo = workspace
    updated = save(client, review, source_readings=[reading()])
    note = updated["commitment_changes"][0]["source_readings"][0]
    content = GitRepository(repo).snapshot_file(review["target_ref"], "checkout.py")["content"]
    assert note["excerpt"] == "\n".join(content.splitlines()[:2])
    assert note["version_ref"] == review["target_ref"]
    assert len(updated["evidence"]) == len(review["evidence"])
    assert decide(client, updated).status_code == 409
    assert client.get(f"/api/reviews/{review['id']}").json()["commitment_changes"][0]["source_readings"] == [note]


@pytest.mark.parametrize("note", [reading(path="../secret"), reading(path="pricing_v2.py"),
    reading(start_line=999, end_line=1000), reading(start_line=2, end_line=1),
    reading(start_line=1, end_line=30), reading(summary=" "), reading(excerpt="invented code")])
def test_invalid_source_readings_cannot_be_saved(workspace, note):
    client, _, review, _ = workspace
    response = client.post(f"/api/reviews/{review['id']}/commitments", json=proposal(review, source_readings=[note]))
    assert response.status_code == 422, response.text
    assert client.get(f"/api/reviews/{review['id']}").json()["revision"] == review["revision"]


def test_editing_preserves_omitted_readings_and_can_explicitly_clear_them(workspace):
    client, _, review, _ = workspace
    first = save(client, review, source_readings=[reading()])
    cid = first["commitment_changes"][0]["after"]["id"]
    second = save(client, first, commitment_id=cid, reason="Clarify the baseline assumptions before acceptance.")
    assert second["commitment_changes"][0]["source_readings"] == first["commitment_changes"][0]["source_readings"]
    third = save(client, second, commitment_id=cid, source_readings=[])
    assert third["commitment_changes"][0]["source_readings"] == []
