import base64
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

from fastapi.testclient import TestClient

from system.domain.models import DecisionAction
from system.services.llm import EvidenceSummarizer, SummaryResult
from system.web.app import create_app as create_secure_app
from tests.helpers import create_alternate_target, create_billing_repo, create_capability_repo


def create_app(database_path: Path):
    """Keep business-contract tests independent from the authentication contract."""
    return create_secure_app(database_path, require_authentication=False)


def test_api_exposes_review_package_and_blocks_unsafe_commit(tmp_path: Path):
    repo, base, target = create_billing_repo(tmp_path)
    with TestClient(create_app(tmp_path / "api.db")) as client:
        project_response = client.post(
            "/api/projects",
            json={
                "name": "Billing",
                "repo_path": str(repo),
                "head_ref": base,
                "test_command": ["python3", "-m", "unittest", "-q"],
                "claims": [
                    {
                        "id": "billing.no_new_legacy_reads",
                        "title": "No new legacy billing reads",
                        "forbidden_modules": ["legacy.billing"],
                    }
                ],
            },
        )
        assert project_response.status_code == 201
        project_id = project_response.json()["id"]

        review_response = client.post(
            f"/api/projects/{project_id}/reviews",
            json={"base_ref": base, "target_ref": target},
        )
        assert review_response.status_code == 201
        review = review_response.json()
        assert review["findings"][0]["kind"] == "forbidden_dependency"

        decision = client.post(
            f"/api/reviews/{review['id']}/decisions",
            json={"action": "commit", "actor": "lead"},
        )
        assert decision.status_code == 409
        assert "critical" in decision.json()["detail"]

        detail = client.get(f"/api/reviews/{review['id']}")
        assert detail.status_code == 200
        assert detail.json()["patch_summary"]


def test_project_tree_uses_the_governed_git_snapshot_and_omits_workspace_noise(
    tmp_path: Path,
):
    repo, base, _target = create_billing_repo(tmp_path)
    create_alternate_target(
        repo,
        base,
        path="future/only-after-base.py",
        content="VALUE = 'not governed yet'\n",
        message="add a file after the governed snapshot",
    )
    (repo / "scratch-notes.txt").write_text("untracked\n", encoding="utf-8")

    with TestClient(create_app(tmp_path / "project-tree.db")) as client:
        project = client.post(
            "/api/projects",
            json={
                "name": "Snapshot tree",
                "repo_path": str(repo),
                "head_ref": base,
                "test_command": [],
                "claims": [],
            },
        ).json()

        response = client.get(f"/api/projects/{project['id']}/tree")
        assert response.status_code == 200
        tree = response.json()
        assert tree["project_id"] == project["id"]
        assert tree["ref"] == base
        assert tree["revision"] == base
        assert tree["truncated"] is False
        entries = {(item["kind"], item["path"]) for item in tree["entries"]}
        assert ("directory", "legacy") in entries
        assert ("file", "legacy/billing.py") in entries
        assert ("file", "checkout.py") in entries
        assert not any(path.startswith(".git") for _kind, path in entries)
        assert not any(path.startswith("future") for _kind, path in entries)
        assert not any(path == "scratch-notes.txt" for _kind, path in entries)

        missing = client.get("/api/projects/project-missing/tree")
        assert missing.status_code == 404
        assert missing.json()["detail"] == "project not found"


def test_concurrent_summary_cannot_overwrite_a_governed_review_transition(
    tmp_path: Path, monkeypatch
):
    repo, base, target = create_billing_repo(tmp_path)
    app = create_app(tmp_path / "summary-concurrency.db")
    summary_started = Event()
    release_summary = Event()

    def blocking_summary(_summarizer, _data):
        summary_started.set()
        assert release_summary.wait(timeout=5)
        return SummaryResult(
            summary="Advisory summary computed from the original open review.",
            source="deterministic",
            provider="test_rules",
        )

    monkeypatch.setattr(EvidenceSummarizer, "summarize", blocking_summary)
    with TestClient(app) as client:
        project = client.post(
            "/api/projects",
            json={
                "name": "Summary concurrency",
                "repo_path": str(repo),
                "head_ref": base,
                "test_command": ["python3", "-m", "unittest", "-q"],
                "claims": [],
            },
        ).json()
        review = client.post(
            f"/api/projects/{project['id']}/reviews",
            json={"base_ref": base, "target_ref": target},
        ).json()

        with ThreadPoolExecutor(max_workers=1) as pool:
            pending_summary = pool.submit(
                client.post, f"/api/reviews/{review['id']}/summary"
            )
            assert summary_started.wait(timeout=5)
            app.state.review_service.decide(
                review["id"],
                DecisionAction(
                    action="reject",
                    actor="lead",
                    reason="The governed review was rejected while summarization was running",
                ),
            )
            release_summary.set()
            summary_response = pending_summary.result(timeout=5)

        assert summary_response.status_code == 409
        assert "concurrent review update" in summary_response.json()["detail"]
        stored = app.state.database.get_review(review["id"])
        assert stored.status == "rejected"
        assert stored.revision == 2
        assert [event.action for event in app.state.database.list_events(review["id"])] == [
            "create_review",
            "reject",
        ]


def test_browser_shell_is_a_real_operator_console(tmp_path: Path):
    with TestClient(create_app(tmp_path / "ui.db")) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "AgenticConsensus" in response.text
        assert "Agentic <b>Consensus</b>" in response.text
        assert "Agentic <b>Consensus</b>" in response.text
        assert "CONSENSUS <b>CONTROL</b>" not in response.text
        assert '/static/app.css?v=' in response.text
        assert '/static/theme.css?v=' in response.text
        assert '/static/theme-bootstrap.js?v=0.17.0-review-desk' in response.text
        assert '/static/app.js?v=' in response.text
        assert '/static/i18n.js?v=' in response.text
        assert client.get('/static/i18n.js').status_code == 200
        assert '/static/decision-model.js?v=' in response.text
        assert response.text.index('/static/decision-model.js') < response.text.index('/static/app.js')
        assert client.get('/static/decision-model.js').status_code == 200
        assert response.text.index('/static/navigation-model.js') < response.text.index('/static/app.js')
        assert client.get('/static/navigation-model.js').status_code == 200
        assert "New review" in response.text
        assert "project-switcher" in response.text
        assert client.get("/static/app.css").status_code == 200
        assert client.get("/static/theme.css").status_code == 200
        assert client.get("/static/theme.css").headers["cache-control"] == "no-cache"
        assert client.get("/static/canvas-model.js").status_code == 200
        assert client.get("/static/theme-bootstrap.js").status_code == 200
        assert client.get("/openapi.json").json()["info"]["version"] == "0.22.3"
        assert 'id="trust-proof-template-button"' in response.text
        assert 'id="trust-proof-download-button"' in response.text
        assert 'id="trust-proof-contract"' in response.text
        javascript = client.get("/static/app.js").text
        assert "trust-roots/possession-template" in javascript
        assert "buildTrustRootFromForm" in javascript
        assert "downloadTrustSigningPackage" in javascript


def test_api_builds_the_exact_trust_root_possession_signing_template(tmp_path: Path):
    repo, base, _ = create_capability_repo(tmp_path)
    with TestClient(create_app(tmp_path / "proof-template-api.db")) as client:
        project = client.post(
            "/api/projects",
            json={
                "name": "Capability migration",
                "repo_path": str(repo),
                "head_ref": base,
                "claims": [],
                "policy_id": "security-change-control/v1",
                "default_authority": "security owner",
            },
        ).json()
        response = client.post(
            f"/api/projects/{project['id']}/trust-roots/possession-template",
            json={
                "new_root": {
                    "key_id": "ci-source-ed25519-2027",
                    "public_key_base64": base64.b64encode(bytes(range(32))).decode(),
                    "verifier_id": "https://ci.example.test/verifiers/source-policy/v1",
                    "authority": "security owner",
                    "resource_uri_prefix": "git+https://example.test/acme/capability@",
                }
            },
        )

        assert response.status_code == 200
        template = response.json()
        assert template["contract"]["project_version"] == project["version"]
        assert template["contract"]["project_head"] == project["head_ref"]
        assert template["contract"]["public_key_base64"] == base64.b64encode(
            bytes(range(32))
        ).decode()
        assert template["contract"]["policy_uri"].endswith("/trust-root-possession/v1")
        assert template["contract"]["required_verified_level"] == (
            "CONSENSUS_TRUST_ROOT_POSSESSION_V1"
        )
        assert template["envelope"]["signatures"][0] == {
            "keyid": "ci-source-ed25519-2027",
            "sig": "<replace-with-base64-ed25519-signature>",
        }
        assert client.get(f"/api/projects/{project['id']}/events").json() == []


def test_project_and_review_boundaries_reject_invalid_duplicates(tmp_path: Path):
    repo, base, target = create_billing_repo(tmp_path)
    with TestClient(create_app(tmp_path / "boundaries.db")) as client:
        empty = client.post(
            "/api/projects",
            json={"name": "   ", "repo_path": str(repo), "head_ref": base, "claims": []},
        )
        assert empty.status_code == 422

        payload = {"name": "Billing", "repo_path": str(repo), "head_ref": base, "claims": []}
        first = client.post("/api/projects", json=payload)
        assert first.status_code == 201
        duplicate = client.post("/api/projects", json=payload)
        assert duplicate.status_code == 409
        assert "already registered" in duplicate.json()["detail"]

        project_id = first.json()["id"]
        review = client.post(
            f"/api/projects/{project_id}/reviews", json={"base_ref": base, "target_ref": target}
        )
        assert review.status_code == 201
        duplicate_review = client.post(
            f"/api/projects/{project_id}/reviews", json={"base_ref": base, "target_ref": target}
        )
        assert duplicate_review.status_code == 409
        assert "already exists" in duplicate_review.json()["detail"]


def test_api_returns_actionable_git_errors_unified_diff_and_runtime_status(tmp_path: Path, monkeypatch):
    repo, base, target = create_billing_repo(tmp_path)
    monkeypatch.setenv("CONSENSUS_LLM_ENABLED", "true")
    monkeypatch.setenv("CONSENSUS_LLM_PROVIDER", "auto")
    monkeypatch.setenv("OPENAI_API_KEY", "not-returned")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")
    with TestClient(create_app(tmp_path / "details.db")) as client:
        project = client.post(
            "/api/projects",
            json={"name": "Billing", "repo_path": str(repo), "head_ref": base, "claims": []},
        ).json()
        invalid = client.post(
            f"/api/projects/{project['id']}/reviews",
            json={"base_ref": base, "target_ref": "missing-branch"},
        )
        assert invalid.status_code == 422
        assert invalid.json()["detail"] == "Git revision not found: missing-branch"

        review = client.post(
            f"/api/projects/{project['id']}/reviews",
            json={"base_ref": base, "target_ref": target},
        ).json()
        diff = client.get(f"/api/reviews/{review['id']}/diff")
        assert diff.status_code == 200
        assert "diff --git" in diff.json()["diff"]
        assert "+from legacy.billing import RATE" in diff.json()["diff"]

        runtime = client.get("/api/runtime")
        assert runtime.status_code == 200
        assert runtime.json()["provider"] == "openai_responses_compatible"
        assert "not-returned" not in runtime.text


def test_dialog_close_controls_bypass_form_validation(tmp_path: Path):
    with TestClient(create_app(tmp_path / "html.db")) as client:
        html = client.get("/").text
        assert html.count('data-close-dialog type="button"') >= 6
        assert 'name="expires_at" type="datetime-local" required' in html
        assert 'name="policy_id"' in html
        assert 'name="default_authority"' in html
        assert 'name="authorized_actors"' in html
        assert 'name="authority"' in html
        javascript = client.get("/static/app.js").text
        assert 'committed: "Approved"' in javascript


def test_operator_console_exposes_the_evidence_obligation_workflow(tmp_path: Path):
    with TestClient(create_app(tmp_path / "obligation-ui.db")) as client:
        html = client.get("/").text
        javascript = client.get("/static/app.js").text
        stylesheet = client.get("/static/app.css").text

        assert 'id="evidence-dialog"' in html
        assert 'id="evidence-form"' in html
        assert 'name="obligation_ids"' in html
        assert 'name="provenance"' in html
        assert "function renderEvidenceObligations" in javascript
        assert "function effectiveFindingStatus" in javascript
        assert "prior waiver expired" in javascript
        assert "data-obligation" in javascript
        assert "`/api/reviews/${reviewId}/evidence`" in javascript
        assert 'actions: ["commit", "waive", "rebase", "reject", "rollback", "attest", "manage_trust"]' in javascript
        assert ".obligation-card" in stylesheet
        assert '.obligation-card[data-status="missing"] .obligation-state' in stylesheet


def test_operator_console_exposes_signed_dsse_configuration_and_import(tmp_path: Path):
    with TestClient(create_app(tmp_path / "dsse-ui.db")) as client:
        html = client.get("/").text
        javascript = client.get("/static/app.js").text

        assert 'name="attestation_public_key_base64"' in html
        assert 'name="attestation_verifier_id"' in html
        assert 'name="signed_obligation_label"' in html
        assert 'id="dsse-dialog"' in html
        assert 'id="dsse-form"' in html
        assert 'name="envelope_json"' in html
        assert 'name="envelope_file"' in html
        assert 'verification === "dsse_ed25519"' in javascript
        assert "function openDsseAttestation" in javascript
        assert "attestation_trust_roots" in javascript
        assert "signed source-policy verification" not in javascript
        assert "`/api/reviews/${reviewId}/attestations/dsse`" in javascript
        assert javascript.count('<p class="delta-summary">${esc(delta.summary)}</p>') == 1


def test_operator_console_exposes_governed_trust_root_lifecycle(tmp_path: Path):
    with TestClient(create_app(tmp_path / "trust-ui.db")) as client:
        html = client.get("/").text
        javascript = client.get("/static/app.js").text
        stylesheet = client.get("/static/app.css").text

        assert 'id="trust-registry"' in html
        assert 'id="trust-root-list"' in html
        assert 'id="project-event-list"' in html
        assert 'id="trust-dialog"' in html
        assert 'id="trust-form"' in html
        assert 'name="new_key_proof_file"' in html
        assert 'name="new_key_proof_json"' in html
        assert "function renderTrustRegistry" in javascript
        assert "function openTrustChange" in javascript
        assert "trust-roots/changes" in javascript
        assert "manage_trust" in javascript
        assert "hasEligibleRoot" in javascript
        assert "trust-root-required" in javascript
        assert ".trust-root-card" in stylesheet
        assert ".trust-event" in stylesheet
        assert "cursor:not-allowed" in stylesheet


def test_api_exposes_reviewer_change_package_without_local_repo_path(tmp_path: Path):
    repo, base, target = create_capability_repo(tmp_path)
    with TestClient(create_app(tmp_path / "reviewer.db")) as client:
        project = client.post(
            "/api/projects",
            json={
                "name": "Capability migration",
                "repo_path": str(repo),
                "repo_label": "demo://capability-migration",
                "head_ref": base,
                "test_command": ["python3", "-m", "unittest", "-q"],
                "claims": [
                    {
                        "id": "authority.task_scoped_only",
                        "title": "Connectors use only task-scoped capabilities",
                        "scope": "connectors.*",
                        "introduced_version": 37,
                        "forbidden_modules": ["legacy.workspace_credentials"],
                        "artifact_anchors": [
                            {"path": "security/task_scope.py", "kind": "code", "relation": "realizes"}
                        ],
                        "evidence_obligations": ["credential provenance trace"],
                        "authority": "security owner",
                    }
                ],
            },
        ).json()
        review = client.post(
            f"/api/projects/{project['id']}/reviews",
            json={
                "base_ref": base,
                "target_ref": target,
                "proposer": "coding-agent/archive-connector",
                "intent_summary": "Add an archive connector without widening credential authority",
            },
        ).json()

        response = client.get(f"/api/reviews/{review['id']}/package")
        assert response.status_code == 200
        package = response.json()
        assert package["notation"]["delta_c"] == 1
        assert package["notation"]["unresolved"] == 1
        assert package["committable"] is False
        assert str(repo) not in response.text
        assert package["repo_label"] == "demo://capability-migration"

        exported = client.get(f"/api/reviews/{review['id']}/export")
        assert exported.status_code == 200
        assert exported.headers["content-disposition"].endswith("-change-package.json\"")
        assert exported.headers["cache-control"] == "no-store"
        assert exported.json()["format"] == "agentic-consensus/change-package@0.7"
        assert exported.json()["manifest"]["package_id"] == review["id"]
        assert exported.json()["project_audit_events"] == []
        assert "repo_path" not in exported.json()["project"]
        assert str(repo) not in exported.text

        html = client.get("/").text
        assert 'id="paper-mode-button"' in html
        assert html.count("autofocus") >= 3


def test_decisions_require_policy_authority_and_persist_a_separate_record(tmp_path: Path):
    repo, base, target = create_billing_repo(tmp_path)
    with TestClient(create_app(tmp_path / "authority.db")) as client:
        project = client.post(
            "/api/projects",
            json={
                "name": "Billing authority",
                "repo_path": str(repo),
                "head_ref": base,
                "test_command": ["python3", "-m", "unittest", "-q"],
                "claims": [],
                "policy_id": "billing-change-control/v1",
                "default_authority": "billing owner",
                "authority_grants": [
                    {
                        "authority": "billing owner",
                        "actors": ["alice@example.test"],
                        "actions": ["commit", "waive", "rebase", "reject", "rollback"],
                    }
                ],
            },
        ).json()
        review = client.post(
            f"/api/projects/{project['id']}/reviews",
            json={"base_ref": base, "target_ref": target, "intent_summary": "Update checkout"},
        ).json()

        outsider = client.post(
            f"/api/reviews/{review['id']}/decisions",
            json={
                "action": "commit",
                "actor": "mallory@example.test",
                "authority": "billing owner",
                "policy_id": "billing-change-control/v1",
                "reason": "Reviewed the complete evidence package",
            },
        )
        assert outsider.status_code == 409
        assert "not authorized" in outsider.json()["detail"]

        wrong_policy = client.post(
            f"/api/reviews/{review['id']}/decisions",
            json={
                "action": "commit",
                "actor": "alice@example.test",
                "authority": "billing owner",
                "policy_id": "different-policy/v1",
                "reason": "Reviewed the complete evidence package",
            },
        )
        assert wrong_policy.status_code == 409
        assert "governing policy" in wrong_policy.json()["detail"]

        admitted = client.post(
            f"/api/reviews/{review['id']}/decisions",
            json={
                "action": "commit",
                "actor": "alice@example.test",
                "authority": "billing owner",
                "policy_id": "billing-change-control/v1",
                "reason": "Reviewed the complete evidence package",
            },
        )
        assert admitted.status_code == 200
        record = admitted.json()["decision_records"][-1]
        assert record["action"] == "commit"
        assert record["actor"] == "alice@example.test"
        assert record["authority"] == "billing owner"
        assert record["policy_id"] == "billing-change-control/v1"
        assert record["provenance"] == "project_authority_grant"

        exported = client.get(f"/api/reviews/{review['id']}/export").json()
        assert exported["review"]["decision_records"][-1]["id"] == record["id"]
        assert exported["manifest"]["governing_policy"] == "billing-change-control/v1"
        assert exported["manifest"]["required_authorities"] == ["billing owner"]


def test_api_attaches_authorized_evidence_to_a_declared_obligation(tmp_path: Path):
    repo, base, target = create_billing_repo(tmp_path)
    with TestClient(create_app(tmp_path / "evidence-api.db")) as client:
        project = client.post(
            "/api/projects",
            json={
                "name": "Evidence API",
                "repo_path": str(repo),
                "head_ref": base,
                "test_command": ["python3", "-m", "unittest", "-q"],
                "policy_id": "billing-change-control/v1",
                "default_authority": "security owner",
                "authority_grants": [
                    {
                        "authority": "security owner",
                        "actors": ["alice"],
                        "actions": ["commit", "waive", "attest"],
                    }
                ],
                "claims": [
                    {
                        "id": "billing.no_new_legacy_reads",
                        "title": "No new legacy billing reads",
                        "forbidden_modules": ["legacy.billing"],
                        "authority": "security owner",
                        "evidence_obligations": [
                            {
                                "label": "credential provenance for the target revision",
                                "required_provenance_prefix": "trusted-runner/",
                            }
                        ],
                    }
                ],
            },
        ).json()
        review = client.post(
            f"/api/projects/{project['id']}/reviews",
            json={"base_ref": base, "target_ref": target},
        ).json()
        obligation_id = review["evidence_obligations"][0]["id"]
        payload = {
            "actor": "mallory",
            "authority": "security owner",
            "policy_id": "billing-change-control/v1",
            "obligation_ids": [obligation_id],
            "summary": "Trusted evidence was reviewed for the target revision",
            "provenance": "trusted-runner/credential-trace-044",
        }

        denied = client.post(f"/api/reviews/{review['id']}/evidence", json=payload)
        assert denied.status_code == 409
        assert "not authorized" in denied.json()["detail"]

        payload["actor"] = "alice"
        attached = client.post(f"/api/reviews/{review['id']}/evidence", json=payload)
        assert attached.status_code == 200
        body = attached.json()
        assert body["revision"] == 2
        assert body["evidence"][-1]["artifact_ref"] == target
        assert body["evidence"][-1]["obligation_ids"] == [obligation_id]

        package = client.get(f"/api/reviews/{review['id']}/package").json()
        assert package["obligation_statuses"][0]["status"] == "satisfied"
