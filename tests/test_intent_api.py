from pathlib import Path
import json
import shutil
import subprocess

import pytest

from fastapi.testclient import TestClient

from system.web.app import create_app

from .helpers import create_billing_repo
from .test_round_trip_realization import _create_round_trip_repo


def _browser_revision_payload(intent, **values):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the real browser payload contract")
    model = Path(__file__).resolve().parents[1] / "system/web/static/intent-model.js"
    result = subprocess.run(
        [node, "-e", "const m=require(process.argv[1]);const p=JSON.parse(process.argv[2]);process.stdout.write(JSON.stringify(m.revisionPayload(p.intent,p.values)));", str(model), json.dumps({"intent": intent, "values": values})],
        check=True, capture_output=True, text=True,
    )
    return json.loads(result.stdout)


def test_browser_proposal_payload_records_revisions_and_additions_without_selection(tmp_path: Path):
    repo, base, _ = create_billing_repo(tmp_path)
    checkout_before = (repo / "checkout.py").read_text()
    with TestClient(create_app(tmp_path / "browser-revision.db", require_authentication=False)) as client:
        project = client.post("/api/projects", json={"name": "Revision contract", "repo_path": str(repo), "head_ref": base, "claims": []}).json()
        intent = client.post(f"/api/projects/{project['id']}/intents", json={"request": "Remove the legacy billing dependency.", "context": "Keep the rate semantics.", "base_ref": base, "candidates": [_candidate("Direct path", "billing.pricing"), _candidate("Adapter", "billing.compat")]}).json()
        original = intent["candidates"][0]
        fields = {"title": original["title"], "summary": original["summary"], **original["structural_delta"], "to_module": "billing.pricing_v2", "uncertainties": "\n".join(original["uncertainties"])}
        payload = _browser_revision_payload(intent, candidateId=original["id"], values=fields, reason="The owner confirmed the versioned contract.")
        saved = client.post(f"/api/intents/{intent['id']}/clarifications", json=payload)
        assert saved.status_code == 200
        revised = saved.json()
        assert revised["revision"] == 2
        assert revised["selected_candidate_id"] is None
        assert revised["realization_attempts"] == []
        assert revised["candidates"][1] == intent["candidates"][1]
        assert revised["candidates"][0]["uncertainties"] == original["uncertainties"]
        turn = revised["clarification_history"][0]
        assert turn["before_candidates"] == intent["candidates"]
        assert turn["after_candidates"] == revised["candidates"]
        assert turn["actor"] == "test-auth-bypass"
        assert client.post(f"/api/intents/{intent['id']}/clarifications", json=payload).status_code == 409

        addition = _browser_revision_payload(revised, values={**fields, "title": "Bounded adapter", "to_module": "billing.bounded_adapter"}, reason="Keep an additional bounded interpretation open.")
        response = client.post(f"/api/intents/{intent['id']}/clarifications", json=addition)
        assert response.status_code == 200
        updated = client.get(f"/api/intents/{intent['id']}").json()
        assert len(updated["candidates"]) == 3
        assert updated["candidates"][-1]["status"] == "active"
        assert updated["candidates"][-1]["provenance"] == "human-authored/added-alternative"
        assert updated["clarification_history"][-1]["added_candidate_ids"] == [updated["candidates"][-1]["id"]]
        assert updated["selected_candidate_id"] is None
        assert updated["realized_review_id"] is None
        assert client.get(f"/api/projects/{project['id']}/reviews").json() == []
        assert (repo / "checkout.py").read_text() == checkout_before


def _candidate(title: str, target_module: str):
    return {
        "title": title,
        "summary": f"Replace legacy.billing with {target_module}.",
        "structural_delta": {
            "kind": "python_import_substitution",
            "path": "checkout.py",
            "from_module": "legacy.billing",
            "to_module": target_module,
        },
        "uncertainties": [f"Validate {target_module} rate semantics"],
        "provenance": f"agent/{target_module}",
    }


def test_intent_workspace_api_runs_create_clarify_select_flow(tmp_path: Path):
    repo, base, _ = create_billing_repo(tmp_path)
    app = create_app(tmp_path / "intent-api.db", require_authentication=False)
    with TestClient(app) as client:
        project = client.post(
            "/api/projects",
            json={
                "name": "Billing",
                "repo_path": str(repo),
                "head_ref": base,
                "claims": [],
            },
        ).json()
        created_response = client.post(
            f"/api/projects/{project['id']}/intents",
            json={
                "request": "Remove the legacy billing dependency without changing semantics.",
                "context": "Architecture review 17.",
                "base_ref": base,
                "candidates": [
                    _candidate("Use pricing v2", "billing.pricing"),
                    _candidate("Use compatibility adapter", "billing.compat"),
                ],
            },
        )
        assert created_response.status_code == 201
        intent = created_response.json()
        chosen, rejected = intent["candidates"]
        assert intent["created_by"] == "test-auth-bypass"

        clarified_response = client.post(
            f"/api/intents/{intent['id']}/clarifications",
            json={
                "question": "Which contract is committed?",
                "answer": "Use pricing v2.",
                "retained_candidate_ids": [chosen["id"]],
                "eliminated_candidate_ids": [rejected["id"]],
                "resolved_uncertainties": {
                    chosen["id"]: chosen["uncertainties"],
                },
                "expected_revision": 1,
            },
        )
        assert clarified_response.status_code == 200
        assert clarified_response.json()["clarification_history"][0]["actor"] == (
            "test-auth-bypass"
        )

        selected_response = client.post(
            f"/api/intents/{intent['id']}/selection",
            json={
                "candidate_id": chosen["id"],
                "reason": "The owner confirmed the committed pricing contract.",
                "expected_revision": 2,
            },
        )
        assert selected_response.status_code == 200
        assert selected_response.json()["selection_actor"] == "test-auth-bypass"

        listed = client.get(f"/api/projects/{project['id']}/intents")
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()] == [intent["id"]]


def test_operator_console_contains_intent_and_clarification_workspace(tmp_path: Path):
    with TestClient(create_app(tmp_path / "intent-ui.db", require_authentication=False)) as client:
        html = client.get("/").text
        javascript = client.get("/static/app.js").text
        stylesheet = client.get("/static/app.css").text

        assert 'id="intent-workspace"' in html
        assert 'id="new-intent-button"' in html
        assert 'id="intent-dialog"' in html
        assert 'id="clarification-dialog"' in html
        assert "function renderIntentWorkspace" in javascript
        assert "function openClarification" in javascript
        assert "function selectIntentCandidate" in javascript
        assert "function realizeIntent" in javascript
        assert "function renderIntentRealization" in javascript
        assert "round_trip_discrepancy" in javascript
        assert "observable_coverage" in javascript
        assert "rehydrated_candidates" in javascript
        assert "unobservable_relations" in javascript
        assert "artifact_diff" in javascript
        assert "realized_review_id" in javascript
        assert "`/api/projects/${projectId}/intents`" in javascript
        assert "`/api/intents/${intentId}/clarifications`" in javascript
        assert "`/api/intents/${intentId}/realization`" in javascript
        assert ".intent-workspace" in stylesheet
        assert ".intent-realization" in stylesheet


def test_intent_api_realizes_selected_candidate_into_linked_review(tmp_path: Path):
    repo, base = _create_round_trip_repo(tmp_path)
    app = create_app(tmp_path / "intent-realization-api.db", require_authentication=False)
    with TestClient(app) as client:
        project = client.post(
            "/api/projects",
            json={
                "name": "Pricing migration",
                "repo_path": str(repo),
                "head_ref": base,
                "test_command": ["python3", "-m", "unittest", "-q"],
                "claims": [],
            },
        ).json()
        intent = client.post(
            f"/api/projects/{project['id']}/intents",
            json={
                "request": "Remove the legacy billing dependency.",
                "context": "Architecture review 17.",
                "base_ref": base,
                "candidates": [
                    _candidate("Use pricing v2", "billing.pricing"),
                    _candidate("Use compatibility adapter", "billing.compat"),
                ],
            },
        ).json()
        chosen, rejected = intent["candidates"]
        clarified = client.post(
            f"/api/intents/{intent['id']}/clarifications",
            json={
                "question": "Which module is committed?",
                "answer": "Use billing.pricing.",
                "retained_candidate_ids": [chosen["id"]],
                "eliminated_candidate_ids": [rejected["id"]],
                "resolved_uncertainties": {chosen["id"]: chosen["uncertainties"]},
                "expected_revision": 1,
            },
        ).json()
        selected = client.post(
            f"/api/intents/{intent['id']}/selection",
            json={
                "candidate_id": chosen["id"],
                "reason": "The owner confirmed the pricing contract.",
                "expected_revision": clarified["revision"],
            },
        ).json()

        response = client.post(
            f"/api/intents/{intent['id']}/realization",
            json={"expected_revision": selected["revision"]},
        )

        assert response.status_code == 200
        realized = response.json()
        assert realized["status"] == "realized"
        assert realized["realization_attempts"][-1]["actor"] == "test-auth-bypass"
        review = client.get(f"/api/reviews/{realized['realized_review_id']}").json()
        assert review["intent_id"] == intent["id"]
        assert review["round_trip_discrepancy"] == 0
