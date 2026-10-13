from fastapi.testclient import TestClient
import pytest

from system.services.auth import DevelopmentIdentity
from system.web.app import create_app, deployment_app_options


IDENTITY = DevelopmentIdentity(actor="Research reviewer", username="reviewer", password="synthetic-test-password-only")


def demo(tmp_path, *, dispatch=True):
    return create_app(tmp_path / "paper.db", paper_demo=True,
                      development_identity=IDENTITY, development_session_secret="test-only-signing-secret-32-characters", paper_demo_dispatch=dispatch)


def test_paper_demo_requires_nondefault_credentials(tmp_path):
    with pytest.raises(ValueError, match="credentials"):
        create_app(tmp_path / "unsafe.db", paper_demo=True)


def test_paper_demo_is_english_seeded_and_blocks_unrelated_execution(tmp_path):
    with TestClient(demo(tmp_path, dispatch=False)) as client:
        state = client.get("/api/auth/state").json()
        assert state["paper_demo"] and not state["setup_required"]
        assert 'data-default-language="en"' in client.get("/").text
        assert client.get("/api/projects").status_code == 401
        auth = client.post("/api/auth/login", json={"username": IDENTITY.username, "password": IDENTITY.password}).json()
        headers = {"X-CSRF-Token": auth["csrf_token"]}
        projects = client.get("/api/projects").json()
        assert len(projects) == 1 and projects[0]["name"] == "StudyShare"
        review = client.get(f"/api/projects/{projects[0]['id']}/reviews").json()[0]
        assert not any("\u4e00" <= char <= "\u9fff" for char in str(review))
        assert client.post("/api/projects", headers=headers, json={"name":"No", "repo_path":"/tmp"}).status_code == 403
        assert client.post("/api/github/app/setup", headers=headers, json={}).status_code == 403
        assert client.post(f"/api/reviews/{review['id']}/tests", headers=headers,
                           json={"test_command":["python3", "-c", "print('arbitrary code')"]}).status_code == 403
        draft = client.post(f"/api/reviews/{review['id']}/commitment-draft", headers=headers,
                            json={"expected_revision":review["revision"], "language":"en"})
        assert draft.status_code == 200
        assert client.post(f"/api/reviews/{review['id']}/revisions", headers=headers,
                           json={"target_ref":"HEAD", "expected_revision":review["revision"]}).status_code == 403
        assert client.post("/api/auth/users", headers=headers, json={}).status_code == 403
        assert client.get(f"/api/reviews/{review['id']}").json()["decision_records"] == []


def test_production_paper_demo_is_explicit_and_keeps_preview_auth_guard(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.setenv("AGENTIC_CONSENSUS_PAPER_DEMO", "true")
    monkeypatch.setenv("AGENTIC_CONSENSUS_PAPER_DEMO_PASSWORD", IDENTITY.password)
    monkeypatch.setenv("AGENTIC_CONSENSUS_PAPER_DEMO_SECRET", "test-only-signing-secret-32-characters")
    options = deployment_app_options()
    assert options["paper_demo"] and options["secure_cookies"]
    assert options["development_identity"].username == "reviewer"
    monkeypatch.delenv("AGENTIC_CONSENSUS_PAPER_DEMO_PASSWORD")
    with pytest.raises(RuntimeError, match="credentials"):
        deployment_app_options()
