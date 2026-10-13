from __future__ import annotations

import sqlite3
import re
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import system.main as main_module
import system.web.app as web_app_module
from system.main import build_parser, main
from system.services.auth import AuthService, DevelopmentIdentity
from system.services.database import Database, database_runtime_lock
from system.web.app import create_app
from tests.helpers import create_billing_repo


ADMIN_PASSWORD = "correct horse battery staple"


def bootstrap(
    client: TestClient,
    *,
    username: str = "alice",
    actor: str = "alice@example.test",
) -> dict:
    response = client.post(
        "/api/auth/bootstrap",
        json={"username": username, "actor": actor, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 201, response.text
    return response.json()


def csrf_headers(auth: dict) -> dict[str, str]:
    return {"X-CSRF-Token": auth["csrf_token"]}


def test_first_run_bootstrap_protects_api_and_issues_server_session(tmp_path: Path):
    app = create_app(tmp_path / "auth-bootstrap.db")
    with TestClient(app) as client:
        state = client.get("/api/auth/state")
        assert state.status_code == 200
        assert state.json() == {
            "setup_required": True,
            "signup_allowed": False,
            "authenticated": False,
            "user": None,
            "csrf_token": None,
        }
        assert client.get("/api/projects").status_code == 401
        weak = client.post(
            "/api/auth/bootstrap",
            json={"username": "alice", "actor": "alice@example.test", "password": "too-short"},
        )
        assert weak.status_code == 422

        auth = bootstrap(client)
        cookie = client.cookies.get("consensus_session")
        assert cookie and len(cookie) >= 40
        login = client.post(
            "/api/auth/login",
            json={"username": "alice", "password": ADMIN_PASSWORD},
        )
        set_cookie = login.headers["set-cookie"]
        assert "HttpOnly" in set_cookie
        assert "SameSite=strict" in set_cookie
        assert "Path=/" in set_cookie
        auth = login.json()
        assert auth["user"] == {
            "id": auth["user"]["id"],
            "username": "alice",
            "actor": "alice@example.test",
            "role": "admin",
            "disabled": False,
            "password_change_required": False,
            "created_at": auth["user"]["created_at"],
        }
        assert "password_hash" not in str(auth).lower()
        assert "current_password" not in str(auth).lower()

        second = client.post(
            "/api/auth/bootstrap",
            json={
                "username": "second",
                "actor": "second@example.test",
                "password": "another correct horse battery staple",
            },
        )
        assert second.status_code == 409
        assert "already initialized" in second.json()["detail"]

        assert client.post("/api/projects", json={}).status_code == 403
        assert client.post(
            "/api/projects", json={}, headers=csrf_headers(auth)
        ).status_code == 422

        assert client.post("/api/auth/logout").status_code == 403
        logout = client.post("/api/auth/logout", headers=csrf_headers(auth))
        assert logout.status_code == 204
        assert client.get("/api/projects").status_code == 401


def test_explicit_development_identity_bootstraps_local_admin_without_relaxing_product_policy(
    tmp_path: Path, monkeypatch,
):
    database_path = tmp_path / "development-auth.db"
    observed = {}

    def inspect_running_app(app, **kwargs):
        observed["server"] = kwargs
        with TestClient(app) as client:
            state = client.get("/api/auth/state").json()
            assert state["setup_required"] is False
            assert state["authenticated"] is False

            login = client.post(
                "/api/auth/login",
                json={"username": "admin", "password": "admin"},
            )
            assert login.status_code == 200, login.text
            observed["user"] = login.json()["user"]

    monkeypatch.setattr(main_module.uvicorn, "run", inspect_running_app)
    assert main(
        [
            "--database",
            str(database_path),
            "serve",
            "--development-auth",
            "--development-audit-identity",
            "developer@example.test",
        ]
    ) == 0
    assert observed["server"] == {
        "host": "127.0.0.1",
        "port": 8765,
        "log_level": "info",
        "access_log": False,
    }
    assert observed["user"] == {
        "id": observed["user"]["id"],
        "username": "admin",
        "actor": "developer@example.test",
        "role": "admin",
        "disabled": False,
        "password_change_required": False,
        "created_at": observed["user"]["created_at"],
    }

    event = Database(database_path).list_auth_events()[0]
    assert event["action"] == "auth_bootstrap"
    assert event["actor"] == "developer@example.test"
    assert event["payload"] == {
        "target_actor": "developer@example.test",
        "target_role": "admin",
    }

    with TestClient(create_app(tmp_path / "product-auth.db")) as client:
        weak = client.post(
            "/api/auth/bootstrap",
            json={
                "username": "admin",
                "actor": "developer@example.test",
                "password": "admin",
            },
        )
        assert weak.status_code == 422


def test_vercel_preview_can_explicitly_bootstrap_the_default_admin(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", "preview")
    monkeypatch.setenv("AGENTIC_CONSENSUS_PREVIEW_DEVELOPMENT_AUTH", "true")
    monkeypatch.setenv(
        "AGENTIC_CONSENSUS_PREVIEW_AUDIT_IDENTITY", "wtfly2018@gmail.com"
    )
    monkeypatch.setenv("AGENTIC_CONSENSUS_PREVIEW_SESSION_SECRET", "s" * 64)
    monkeypatch.setenv("AGENTIC_CONSENSUS_PREVIEW_SELF_SIGNUP", "true")

    options = web_app_module.deployment_app_options()
    assert options["allow_self_signup"] is True
    options.pop("database_path")
    with TestClient(
        create_app(tmp_path / "vercel-preview.db", **options),
        base_url="https://control.example.test",
    ) as client:
        state = client.get("/api/auth/state").json()
        login = client.post(
            "/api/auth/login", json={"username": "admin", "password": "admin"}
        )

    assert state["setup_required"] is False
    assert login.status_code == 200
    assert login.json()["user"]["actor"] == "wtfly2018@gmail.com"
    assert "__Host-consensus_session=" in login.headers["set-cookie"]
    assert "Secure" in login.headers["set-cookie"]


def test_vercel_runtime_uses_a_writable_ephemeral_database(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.delenv("AGENTIC_CONSENSUS_PREVIEW_DEVELOPMENT_AUTH", raising=False)

    options = web_app_module.deployment_app_options()

    assert options["database_path"] == Path(
        "/tmp/agentic-consensus/agentic-consensus.db"
    )


def test_self_signup_requires_an_initialized_opted_in_instance(tmp_path: Path):
    with TestClient(create_app(tmp_path / "signup-disabled.db")) as disabled:
        response = disabled.post(
            "/api/auth/signup",
            json={
                "username": "builder",
                "actor": "builder@example.test",
                "password": ADMIN_PASSWORD,
            },
        )
    assert response.status_code == 403

    with TestClient(
        create_app(tmp_path / "signup-first-admin.db", allow_self_signup=True)
    ) as uninitialized:
        response = uninitialized.post(
            "/api/auth/signup",
            json={
                "username": "builder",
                "actor": "builder@example.test",
                "password": ADMIN_PASSWORD,
            },
        )
    assert response.status_code == 409
    assert "first administrator" in response.json()["detail"]


def test_signup_creates_an_operator_and_supports_a_signout_signin_cycle(tmp_path: Path):
    app = create_app(tmp_path / "signup.db", allow_self_signup=True)
    with TestClient(app) as client:
        admin = bootstrap(client)
        client.post("/api/auth/logout", headers=csrf_headers(admin))

        signup = client.post(
            "/api/auth/signup",
            json={
                "username": "builder",
                "actor": "builder@example.test",
                "password": ADMIN_PASSWORD,
            },
        )
        assert signup.status_code == 201, signup.text
        auth = signup.json()
        assert auth["user"]["role"] == "operator"
        assert auth["user"]["password_change_required"] is False
        assert client.get("/api/projects").status_code == 200

        client.post("/api/auth/logout", headers=csrf_headers(auth))
        login = client.post(
            "/api/auth/login",
            json={"username": "builder", "password": ADMIN_PASSWORD},
        )
        duplicate = client.post(
            "/api/auth/signup",
            json={
                "username": "builder",
                "actor": "another-builder@example.test",
                "password": ADMIN_PASSWORD,
            },
        )

    assert login.status_code == 200
    assert login.json()["user"]["actor"] == "builder@example.test"
    assert duplicate.status_code == 409


def test_preview_signup_profile_can_sign_in_on_a_fresh_serverless_instance(
    tmp_path: Path,
):
    identity = DevelopmentIdentity(actor="wtfly2018@gmail.com")
    options = {
        "secure_cookies": True,
        "development_identity": identity,
        "development_session_secret": "s" * 64,
        "allow_self_signup": True,
    }

    with TestClient(
        create_app(tmp_path / "signup-instance-a.db", **options),
        base_url="https://control.example.test",
    ) as first:
        signup = first.post(
            "/api/auth/signup",
            json={
                "username": "builder",
                "actor": "builder@example.test",
                "password": ADMIN_PASSWORD,
            },
        )
        assert signup.status_code == 201, signup.text
        portable_account = first.cookies.get("__Host-consensus_demo_account")

    with TestClient(
        create_app(tmp_path / "signup-instance-b.db", **options),
        base_url="https://control.example.test",
    ) as second:
        second.cookies.set(
            "__Host-consensus_demo_account", portable_account, path="/"
        )
        login = second.post(
            "/api/auth/login",
            json={"username": "builder", "password": ADMIN_PASSWORD},
        )
        projects = second.get("/api/projects")

    assert login.status_code == 200
    assert login.json()["user"]["actor"] == "builder@example.test"
    assert projects.status_code == 200


def test_vercel_preview_session_survives_a_fresh_serverless_instance(tmp_path: Path):
    identity = DevelopmentIdentity(actor="wtfly2018@gmail.com")
    options = {
        "secure_cookies": True,
        "development_identity": identity,
        "development_session_secret": "s" * 64,
    }

    with TestClient(
        create_app(tmp_path / "instance-a.db", **options),
        base_url="https://control.example.test",
    ) as first:
        login = first.post(
            "/api/auth/login", json={"username": "admin", "password": "admin"}
        )
        assert login.status_code == 200
        token = first.cookies.get("__Host-consensus_session")

    with TestClient(
        create_app(tmp_path / "instance-b.db", **options),
        base_url="https://control.example.test",
    ) as second:
        second.cookies.set("__Host-consensus_session", token, path="/")
        state = second.get("/api/auth/state")
        projects = second.get("/api/projects")

    assert state.status_code == 200
    assert state.json()["authenticated"] is True
    assert state.json()["user"]["actor"] == "wtfly2018@gmail.com"
    assert projects.status_code == 200


def test_vercel_preview_rejects_a_tampered_stateless_session(tmp_path: Path):
    identity = DevelopmentIdentity(actor="wtfly2018@gmail.com")
    app = create_app(
        tmp_path / "tampered.db",
        secure_cookies=True,
        development_identity=identity,
        development_session_secret="s" * 64,
    )

    with TestClient(app, base_url="https://control.example.test") as client:
        client.cookies.set("__Host-consensus_session", "preview.invalid.signature", path="/")
        state = client.get("/api/auth/state")
        projects = client.get("/api/projects")

    assert state.json()["authenticated"] is False
    assert projects.status_code == 401


def test_vercel_preview_requires_a_session_signing_secret(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", "preview")
    monkeypatch.setenv("AGENTIC_CONSENSUS_PREVIEW_DEVELOPMENT_AUTH", "true")
    monkeypatch.setenv(
        "AGENTIC_CONSENSUS_PREVIEW_AUDIT_IDENTITY", "wtfly2018@gmail.com"
    )
    monkeypatch.delenv("AGENTIC_CONSENSUS_PREVIEW_SESSION_SECRET", raising=False)

    with pytest.raises(RuntimeError, match="session signing secret"):
        web_app_module.deployment_app_options()


def test_vercel_production_refuses_preview_development_auth(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.setenv("AGENTIC_CONSENSUS_PREVIEW_DEVELOPMENT_AUTH", "true")
    monkeypatch.setenv(
        "AGENTIC_CONSENSUS_PREVIEW_AUDIT_IDENTITY", "wtfly2018@gmail.com"
    )
    monkeypatch.setenv("AGENTIC_CONSENSUS_PREVIEW_SESSION_SECRET", "s" * 64)

    with pytest.raises(RuntimeError, match="preview development authentication"):
        web_app_module.deployment_app_options()


def test_roles_user_administration_and_disabled_session_enforcement(tmp_path: Path):
    app = create_app(tmp_path / "auth-roles.db")
    with TestClient(app) as client:
        admin = bootstrap(client)
        created = client.post(
            "/api/users",
            headers=csrf_headers(admin),
            json={
                "username": "reviewer",
                "actor": "reviewer@example.test",
                "password": "reviewer correct horse battery staple",
                "role": "viewer",
            },
        )
        assert created.status_code == 201, created.text
        viewer = created.json()
        assert viewer["role"] == "viewer"
        assert viewer["password_change_required"] is True
        assert "password_hash" not in created.text.lower()
        assert "new_password" not in created.text.lower()

        users = client.get("/api/users")
        assert users.status_code == 200
        assert [item["username"] for item in users.json()] == ["alice", "reviewer"]

        client.post("/api/auth/logout", headers=csrf_headers(admin))
        login = client.post(
            "/api/auth/login",
            json={
                "username": "reviewer",
                "password": "reviewer correct horse battery staple",
            },
        )
        assert login.status_code == 200
        reviewer_auth = login.json()
        assert reviewer_auth["user"]["password_change_required"] is True
        forced = client.get("/api/projects")
        assert forced.status_code == 403
        assert forced.json()["detail"] == "password change required"
        changed = client.post(
            "/api/auth/password",
            headers=csrf_headers(reviewer_auth),
            json={
                "current_password": "reviewer correct horse battery staple",
                "new_password": "reviewer updated correct horse battery staple",
            },
        )
        assert changed.status_code == 200, changed.text
        reviewer_auth = changed.json()
        assert reviewer_auth["user"]["password_change_required"] is False
        assert client.get("/api/projects").status_code == 200
        denied = client.post(
            "/api/projects", json={}, headers=csrf_headers(reviewer_auth)
        )
        assert denied.status_code == 403
        assert denied.json()["detail"] == "operator role required"
        assert client.get("/api/users").status_code == 403

        client.post("/api/auth/logout", headers=csrf_headers(reviewer_auth))
        relogin = client.post(
            "/api/auth/login", json={"username": "alice", "password": ADMIN_PASSWORD}
        )
        admin = relogin.json()
        disabled = client.patch(
            f"/api/users/{viewer['id']}",
            headers=csrf_headers(admin),
            json={"disabled": True},
        )
        assert disabled.status_code == 200
        assert disabled.json()["disabled"] is True

        client.post("/api/auth/logout", headers=csrf_headers(admin))
        rejected = client.post(
            "/api/auth/login",
            json={
                "username": "reviewer",
                "password": "reviewer correct horse battery staple",
            },
        )
        assert rejected.status_code == 401
        assert rejected.json()["detail"] == "invalid username or password"


def test_ai_routes_enforce_csrf_roles_and_read_only_viewer_access(tmp_path: Path):
    repo, base, target = create_billing_repo(tmp_path)
    app = create_app(tmp_path / "auth-ai-routes.db")
    with TestClient(app) as client:
        admin = bootstrap(client)
        admin_headers = csrf_headers(admin)
        project = client.post(
            "/api/projects",
            headers=admin_headers,
            json={
                "name": "AI route policy",
                "repo_path": str(repo),
                "head_ref": base,
                "test_command": [],
                "claims": [],
            },
        ).json()
        review = client.post(
            f"/api/projects/{project['id']}/reviews",
            headers=admin_headers,
            json={"base_ref": base, "target_ref": target},
        ).json()
        run = client.post(
            f"/api/reviews/{review['id']}/ai/evidence-gaps",
            headers=admin_headers,
        ).json()

        mutations = [
            (f"/api/reviews/{review['id']}/risk-analysis", {"expected_revision": review['revision']}),
            (f"/api/reviews/{review['id']}/commitment-draft", {"expected_revision": review['revision']}),
            (f"/api/reviews/{review['id']}/revisions", {"expected_revision": review['revision'], "target_ref": target}),
            (
                f"/api/projects/{project['id']}/ai/interpret-intent",
                {
                    "request": "Replace the legacy import in checkout.py",
                    "context": "Preserve runtime behavior",
                    "base_ref": base,
                },
            ),
            (
                f"/api/reviews/{review['id']}/ai/copilot",
                {"question": "What blocks this review?", "deliberate": False},
            ),
            (f"/api/reviews/{review['id']}/ai/evidence-gaps", None),
            (
                f"/api/ai/runs/{run['id']}/feedback",
                {"verdict": "accepted", "note": "Grounded answer"},
            ),
            (
                f"/api/reviews/{review['id']}/tests",
                {"test_command": ["python3", "-m", "unittest", "-q"]},
            ),
        ]
        for path, payload in mutations:
            response = client.post(path, json=payload)
            assert response.status_code == 403
            assert response.json()["detail"] == "valid CSRF token required"

        viewer_password = "reviewer correct horse battery staple"
        viewer = client.post(
            "/api/users",
            headers=admin_headers,
            json={
                "username": "reviewer",
                "actor": "reviewer@example.test",
                "password": viewer_password,
                "role": "viewer",
            },
        ).json()
        client.post("/api/auth/logout", headers=admin_headers)
        viewer_auth = client.post(
            "/api/auth/login",
            json={"username": "reviewer", "password": viewer_password},
        ).json()
        viewer_auth = client.post(
            "/api/auth/password",
            headers=csrf_headers(viewer_auth),
            json={
                "current_password": viewer_password,
                "new_password": "reviewer updated correct horse battery staple",
            },
        ).json()
        viewer_headers = csrf_headers(viewer_auth)

        for path, payload in mutations:
            response = client.post(path, headers=viewer_headers, json=payload)
            assert response.status_code == 403
            assert response.json()["detail"] == "operator role required"

        assert client.get(f"/api/projects/{project['id']}/tree").status_code == 200
        assert client.get(f"/api/projects/{project['id']}/ai/runs").status_code == 200
        assert client.get(f"/api/projects/{project['id']}/ai/evals").status_code == 200

        client.post("/api/auth/logout", headers=viewer_headers)
        assert client.post(
            f"/api/reviews/{review['id']}/ai/evidence-gaps"
        ).status_code == 401
        assert client.get(f"/api/projects/{project['id']}/ai/runs").status_code == 401


def test_password_change_reauthenticates_rotates_session_and_audits(tmp_path: Path):
    app = create_app(tmp_path / "auth-password-change.db")
    with TestClient(app) as primary, TestClient(app) as secondary:
        auth = bootstrap(primary)
        second_auth = secondary.post(
            "/api/auth/login",
            json={"username": "alice", "password": ADMIN_PASSWORD},
        ).json()

        assert primary.post(
            "/api/auth/password",
            json={
                "current_password": ADMIN_PASSWORD,
                "new_password": "a newly rotated correct horse battery staple",
            },
        ).status_code == 403
        wrong = primary.post(
            "/api/auth/password",
            headers=csrf_headers(auth),
            json={
                "current_password": "not the current password",
                "new_password": "a newly rotated correct horse battery staple",
            },
        )
        assert wrong.status_code == 401
        assert wrong.json()["detail"] == "current password is incorrect"
        unchanged = primary.post(
            "/api/auth/password",
            headers=csrf_headers(auth),
            json={"current_password": ADMIN_PASSWORD, "new_password": ADMIN_PASSWORD},
        )
        assert unchanged.status_code == 422
        assert unchanged.json()["detail"] == "new password must differ from current password"

        changed = primary.post(
            "/api/auth/password",
            headers=csrf_headers(auth),
            json={
                "current_password": ADMIN_PASSWORD,
                "new_password": "a newly rotated correct horse battery staple",
            },
        )
        assert changed.status_code == 200, changed.text
        rotated = changed.json()
        assert rotated["csrf_token"] != auth["csrf_token"]
        assert rotated["user"]["password_change_required"] is False
        assert primary.get("/api/projects").status_code == 200
        assert secondary.get("/api/projects").status_code == 401
        assert second_auth["csrf_token"]

        with TestClient(app) as login_client:
            assert login_client.post(
                "/api/auth/login",
                json={"username": "alice", "password": ADMIN_PASSWORD},
            ).status_code == 401
            assert login_client.post(
                "/api/auth/login",
                json={
                    "username": "alice",
                    "password": "a newly rotated correct horse battery staple",
                },
            ).status_code == 200

        events = primary.get("/api/auth/events").json()
        assert [event["action"] for event in events] == [
            "auth_bootstrap",
            "auth_password_change",
        ]
        assert "password" not in str(events[1]["payload"]).lower()


def test_administrator_reset_forces_change_and_revokes_target_sessions(tmp_path: Path):
    app = create_app(tmp_path / "auth-password-reset.db")
    with TestClient(app) as administrator, TestClient(app) as viewer:
        admin_auth = bootstrap(administrator)
        created = administrator.post(
            "/api/users",
            headers=csrf_headers(admin_auth),
            json={
                "username": "reviewer",
                "actor": "reviewer@example.test",
                "password": "reviewer temporary correct horse battery staple",
                "role": "viewer",
            },
        ).json()
        viewer_auth = viewer.post(
            "/api/auth/login",
            json={
                "username": "reviewer",
                "password": "reviewer temporary correct horse battery staple",
            },
        ).json()
        assert viewer_auth["user"]["password_change_required"] is True
        assert viewer.get("/api/projects").json()["detail"] == "password change required"

        self_reset = administrator.post(
            f"/api/users/{admin_auth['user']['id']}/password",
            headers=csrf_headers(admin_auth),
            json={"new_password": "administrator reset should not be permitted"},
        )
        assert self_reset.status_code == 409

        reset = administrator.post(
            f"/api/users/{created['id']}/password",
            headers=csrf_headers(admin_auth),
            json={"new_password": "reviewer reset correct horse battery staple"},
        )
        assert reset.status_code == 200, reset.text
        assert reset.json()["password_change_required"] is True
        assert "password_hash" not in reset.text.lower()
        assert "new_password" not in reset.text.lower()
        assert viewer.get("/api/projects").status_code == 401

        old_login = viewer.post(
            "/api/auth/login",
            json={
                "username": "reviewer",
                "password": "reviewer temporary correct horse battery staple",
            },
        )
        assert old_login.status_code == 401
        new_login = viewer.post(
            "/api/auth/login",
            json={
                "username": "reviewer",
                "password": "reviewer reset correct horse battery staple",
            },
        )
        assert new_login.status_code == 200
        viewer_auth = new_login.json()
        assert viewer_auth["user"]["password_change_required"] is True
        changed = viewer.post(
            "/api/auth/password",
            headers=csrf_headers(viewer_auth),
            json={
                "current_password": "reviewer reset correct horse battery staple",
                "new_password": "reviewer final correct horse battery staple",
            },
        )
        assert changed.status_code == 200
        assert changed.json()["user"]["password_change_required"] is False
        assert viewer.get("/api/projects").status_code == 200

        events = administrator.get("/api/auth/events").json()
        assert [event["action"] for event in events] == [
            "auth_bootstrap",
            "auth_user_create",
            "auth_password_reset",
            "auth_password_change",
        ]
        assert all("password" not in str(event["payload"]).lower() for event in events)


def test_revoke_other_sessions_preserves_current_session_and_is_audited(tmp_path: Path):
    app = create_app(tmp_path / "auth-session-revoke.db")
    with TestClient(app) as primary, TestClient(app) as secondary:
        auth = bootstrap(primary)
        secondary.post(
            "/api/auth/login", json={"username": "alice", "password": ADMIN_PASSWORD}
        )
        revoked = primary.post(
            "/api/auth/sessions/revoke-others", headers=csrf_headers(auth)
        )
        assert revoked.status_code == 200
        assert revoked.json() == {"revoked_sessions": 1}
        assert primary.get("/api/projects").status_code == 200
        assert secondary.get("/api/projects").status_code == 401
        events = primary.get("/api/auth/events").json()
        assert events[-1]["action"] == "auth_sessions_revoke"
        assert events[-1]["payload"] == {
            "target_actor": "alice@example.test",
            "target_role": "admin",
            "revoked_sessions": "1",
        }


def test_login_spray_is_limited_by_client_independently_of_username(tmp_path: Path):
    app = create_app(tmp_path / "auth-spray.db")
    with TestClient(app) as client:
        auth = bootstrap(client)
        client.post("/api/auth/logout", headers=csrf_headers(auth))
        for index in range(20):
            response = client.post(
                "/api/auth/login",
                json={"username": f"unknown-{index}", "password": "incorrect password"},
            )
            assert response.status_code == 401
        blocked = client.post(
            "/api/auth/login", json={"username": "alice", "password": ADMIN_PASSWORD}
        )
        assert blocked.status_code == 429
        assert blocked.json()["detail"] == "too many login attempts"


def test_v09_auth_schema_migrates_without_forcing_existing_accounts(tmp_path: Path):
    database_path = tmp_path / "v09-auth.db"
    with closing(sqlite3.connect(database_path)) as connection:
        with connection:
            connection.execute(
                """CREATE TABLE auth_users (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    username_normalized TEXT NOT NULL UNIQUE,
                    actor TEXT NOT NULL,
                    actor_normalized TEXT NOT NULL UNIQUE,
                    role TEXT NOT NULL CHECK(role IN ('admin', 'operator', 'viewer')),
                    password_hash TEXT NOT NULL,
                    disabled INTEGER NOT NULL DEFAULT 0 CHECK(disabled IN (0, 1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
            )

    app = create_app(database_path)
    with closing(sqlite3.connect(database_path)) as connection:
        columns = {
            row[1]: row for row in connection.execute("PRAGMA table_info(auth_users)")
        }
    assert "password_change_required" in columns
    assert columns["password_change_required"][4] == "0"

    with TestClient(app) as client:
        auth = bootstrap(client)
        assert auth["user"]["password_change_required"] is False


def test_identity_administration_is_append_only_audited_without_credentials(tmp_path: Path):
    app = create_app(tmp_path / "auth-audit.db")
    with TestClient(app) as client:
        admin = bootstrap(client)
        created = client.post(
            "/api/users",
            headers=csrf_headers(admin),
            json={
                "username": "operator",
                "actor": "operator@example.test",
                "password": "operator correct horse battery staple",
                "role": "operator",
            },
        ).json()
        client.patch(
            f"/api/users/{created['id']}",
            headers=csrf_headers(admin),
            json={"disabled": True},
        )

        response = client.get("/api/auth/events")
        assert response.status_code == 200
        events = response.json()
        assert [event["action"] for event in events] == [
            "auth_bootstrap",
            "auth_user_create",
            "auth_user_disable",
        ]
        assert [event["actor"] for event in events] == [
            "alice@example.test",
            "alice@example.test",
            "alice@example.test",
        ]
        assert events[1]["target_user_id"] == created["id"]
        assert events[1]["payload"] == {
            "target_actor": "operator@example.test",
            "target_role": "operator",
        }
        serialized = response.text.lower()
        assert "password" not in serialized
        assert "csrf" not in serialized
        assert "session" not in serialized


def test_authenticated_actor_cannot_be_spoofed_in_governed_decision(tmp_path: Path):
    repo, base, target = create_billing_repo(tmp_path)
    app = create_app(tmp_path / "auth-actor.db")
    with TestClient(app) as client:
        auth = bootstrap(client)
        headers = csrf_headers(auth)
        project = client.post(
            "/api/projects",
            headers=headers,
            json={
                "name": "Authenticated authority",
                "repo_path": str(repo),
                "head_ref": base,
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
            headers=headers,
            json={"base_ref": base, "target_ref": target},
        ).json()

        spoofed = client.post(
            f"/api/reviews/{review['id']}/decisions",
            headers=headers,
            json={
                "action": "reject",
                "actor": "mallory@example.test",
                "authority": "billing owner",
                "policy_id": "billing-change-control/v1",
                "reason": "The proposal should not proceed under the current policy",
            },
        )
        assert spoofed.status_code == 403
        assert spoofed.json()["detail"] == "actor must match authenticated identity"

        admitted = client.post(
            f"/api/reviews/{review['id']}/decisions",
            headers=headers,
            json={
                "action": "reject",
                "actor": "alice@example.test",
                "authority": "billing owner",
                "policy_id": "billing-change-control/v1",
                "reason": "The proposal should not proceed under the current policy",
            },
        )
        assert admitted.status_code == 200
        assert admitted.json()["decision_records"][-1]["actor"] == "alice@example.test"
        assert client.get(f"/api/reviews/{review['id']}/events").json()[-1]["actor"] == (
            "alice@example.test"
        )


def test_login_failures_are_uniform_and_rate_limited(tmp_path: Path):
    app = create_app(tmp_path / "auth-throttle.db")
    with TestClient(app) as client:
        auth = bootstrap(client)
        client.post("/api/auth/logout", headers=csrf_headers(auth))

        known = client.post(
            "/api/auth/login", json={"username": "alice", "password": "incorrect password"}
        )
        unknown = client.post(
            "/api/auth/login", json={"username": "unknown", "password": "incorrect password"}
        )
        assert known.status_code == unknown.status_code == 401
        assert known.json() == unknown.json() == {"detail": "invalid username or password"}

        for _ in range(4):
            client.post(
                "/api/auth/login", json={"username": "alice", "password": "incorrect password"}
            )
        blocked = client.post(
            "/api/auth/login", json={"username": "alice", "password": ADMIN_PASSWORD}
        )
        assert blocked.status_code == 429
        assert int(blocked.headers["retry-after"]) > 0


def test_expired_server_session_and_secure_cookie_mode_fail_closed(tmp_path: Path):
    database_path = tmp_path / "auth-expiry.db"
    app = create_app(database_path, secure_cookies=True)
    with TestClient(app, base_url="https://testserver") as client:
        auth = bootstrap(client)
        set_cookie = client.post(
            "/api/auth/login", json={"username": "alice", "password": ADMIN_PASSWORD}
        )
        assert set_cookie.headers["strict-transport-security"] == (
            "max-age=31536000; includeSubDomains"
        )
        set_cookie = set_cookie.headers["set-cookie"]
        assert "__Host-consensus_session=" in set_cookie
        assert "Secure" in set_cookie
        assert "HttpOnly" in set_cookie
        assert "SameSite=strict" in set_cookie

        with closing(sqlite3.connect(database_path)) as connection:
            with connection:
                connection.execute(
                    "UPDATE auth_sessions SET expires_at = '2000-01-01T00:00:00+00:00'"
                )
        expired = client.get("/api/projects")
        assert expired.status_code == 401
        assert expired.json()["detail"] == "authentication required"
        assert auth["csrf_token"]


def test_serve_requires_secure_cookies_outside_loopback(
    tmp_path: Path, monkeypatch, capsys
):
    calls = []
    monkeypatch.setattr(main_module.uvicorn, "run", lambda *args, **kwargs: calls.append(kwargs))
    database_path = tmp_path / "serve-auth.db"

    unsafe = main(
        [
            "--database",
            str(database_path),
            "serve",
            "--host",
            "0.0.0.0",
            "--port",
            "8877",
        ]
    )
    assert unsafe == 2
    assert "secure cookies" in capsys.readouterr().err.lower()
    assert calls == []

    safe = main(
        [
            "--database",
            str(database_path),
            "serve",
            "--host",
            "0.0.0.0",
            "--port",
            "8877",
            "--secure-cookies",
        ]
    )
    assert safe == 0
    assert calls == [
        {
            "host": "0.0.0.0",
            "port": 8877,
            "log_level": "info",
            "access_log": False,
        }
    ]


def test_development_auth_is_rejected_outside_loopback(tmp_path: Path, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(main_module.uvicorn, "run", lambda *args, **kwargs: calls.append(kwargs))

    result = main(
        [
            "--database",
            str(tmp_path / "non-loopback-development-auth.db"),
            "serve",
            "--host",
            "0.0.0.0",
            "--secure-cookies",
            "--development-auth",
            "--development-audit-identity",
            "developer@example.test",
        ]
    )

    assert result == 2
    assert "development authentication requires a loopback host" in (
        capsys.readouterr().err.lower()
    )
    assert calls == []


def test_operator_console_has_first_run_login_and_user_administration_ui(tmp_path: Path):
    with TestClient(create_app(tmp_path / "auth-ui.db")) as client:
        page_response = client.get("/")
        html = page_response.text
        javascript = client.get("/static/app.js").text
        stylesheet = client.get("/static/app.css").text
        theme_stylesheet = client.get("/static/theme.css").text

    assert page_response.headers["cache-control"] == "no-store"
    assert page_response.headers["x-content-type-options"] == "nosniff"
    assert page_response.headers["x-frame-options"] == "DENY"
    assert page_response.headers["referrer-policy"] == "no-referrer"
    assert page_response.headers["permissions-policy"] == (
        "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
    )
    assert "frame-ancestors 'none'" in page_response.headers["content-security-policy"]
    assert "script-src 'self'" in page_response.headers["content-security-policy"]

    assert 'id="auth-gate"' in html
    assert 'id="bootstrap-form"' in html
    bootstrap_markup = html.split('id="bootstrap-form"', 1)[1].split("</form>", 1)[0]
    assert 'name="confirm_password"' in bootstrap_markup
    assert 'id="login-form"' in html
    login_markup = html.split('id="login-form"', 1)[1].split("</form>", 1)[0]
    assert 'name="username"' in login_markup
    assert 'value="admin"' not in login_markup
    assert 'id="auth-mode-tabs"' in html
    assert 'data-auth-mode="signin"' in html
    assert 'data-auth-mode="signup"' in html
    assert 'id="signup-form"' in html
    signup_markup = html.split('id="signup-form"', 1)[1].split("</form>", 1)[0]
    assert 'name="actor"' in signup_markup
    assert 'name="confirm_password"' in signup_markup
    assert 'id="forced-password-form"' in html
    assert 'id="current-user"' in html
    assert 'id="password-button"' in html
    assert 'id="logout-button"' in html
    assert 'id="users-dialog"' in html
    assert 'id="user-form"' in html
    assert 'id="auth-event-list"' in html
    assert 'id="password-dialog"' in html
    assert 'id="password-form"' in html
    assert 'id="reset-password-dialog"' in html
    assert 'id="reset-password-form"' in html
    assert "Responsible human<input" not in html
    assert "Evidence recorder<input" not in html
    assert 'name="actor"' in html
    assert html.count("<form") == html.count("</form>")

    assert 'api("/api/auth/state")' in javascript
    assert 'api("/api/auth/signup"' in javascript
    assert "function setAuthMode" in javascript
    assert 'data.password !== data.confirm_password' in javascript
    assert "delete data.confirm_password" in javascript
    assert 'headers["X-CSRF-Token"]' in javascript
    assert 'api("/api/auth/logout"' in javascript
    assert 'api("/api/auth/password"' in javascript
    assert 'api("/api/auth/sessions/revoke-others"' in javascript
    assert 'api(`/api/users/${state.resetUser.id}/password`' in javascript
    assert 'api("/api/users")' in javascript
    assert 'api("/api/auth/events")' in javascript
    assert "event.payload.operator" in javascript
    assert "event.payload.reason" in javascript
    assert 'localStorage.setItem("consensus-actor"' not in javascript
    assert "function renderAuthenticatedUser" in javascript
    assert ".auth-gate" in stylesheet
    assert ".user-card" in stylesheet
    assert ".password-required" in stylesheet
    assert "max-height:calc(100vh - 32px)" in stylesheet
    assert re.search(r"\.auth-panel\s*\{[^}]*overflow:\s*auto;", theme_stylesheet)


def test_offline_password_recovery_requires_stopped_console_and_rotates_credential(
    tmp_path: Path, monkeypatch, capsys
):
    database_path = tmp_path / "offline-recovery.db"
    app = create_app(database_path)
    with TestClient(app) as primary, TestClient(app) as secondary:
        bootstrap(primary)
        assert secondary.post(
            "/api/auth/login",
            json={"username": "alice", "password": ADMIN_PASSWORD},
        ).status_code == 200

    recovered_password = "temporary recovered correct horse battery staple"
    monkeypatch.setenv("TEST_RECOVERY_PASSWORD", recovered_password)
    password_reads = 0

    def read_recovery_password(_password_env):
        nonlocal password_reads
        password_reads += 1
        return recovered_password

    monkeypatch.setattr(main_module, "_read_recovery_password", read_recovery_password)
    command = [
        "--database",
        str(database_path),
        "recover-password",
        "--username",
        "alice",
        "--operator",
        "local-host-owner",
        "--reason",
        "Recover the sole administrator after credential loss",
        "--password-env",
        "TEST_RECOVERY_PASSWORD",
    ]

    with database_runtime_lock(database_path):
        assert main(command) == 2
    assert password_reads == 0
    locked_error = capsys.readouterr().err
    assert "still in use" in locked_error

    assert main(command) == 0
    assert password_reads == 1
    captured = capsys.readouterr()
    report = __import__("json").loads(captured.out)
    assert captured.err == ""
    assert recovered_password not in captured.out
    assert "TEST_RECOVERY_PASSWORD" not in captured.out
    assert report["target_actor"] == "alice@example.test"
    assert report["target_role"] == "admin"
    assert report["password_change_required"] is True
    assert report["revoked_sessions"] == 2
    recovery_backup = Path(report["recovery_backup"])
    assert recovery_backup.is_file()
    assert Database.validate_backup(recovery_backup)["health"]["projects"] == 0

    with TestClient(create_app(database_path)) as client:
        assert client.post(
            "/api/auth/login",
            json={"username": "alice", "password": ADMIN_PASSWORD},
        ).status_code == 401
        recovered = client.post(
            "/api/auth/login",
            json={"username": "alice", "password": recovered_password},
        )
        assert recovered.status_code == 200
        assert recovered.json()["user"]["password_change_required"] is True
        assert client.get("/api/projects").json()["detail"] == "password change required"

    event = Database(database_path).list_auth_events()[-1]
    assert event["action"] == "auth_password_recovery"
    assert event["actor"] == "local-maintenance"
    assert event["payload"] == {
        "target_actor": "alice@example.test",
        "target_role": "admin",
        "operator": "local-host-owner",
        "reason": "Recover the sole administrator after credential loss",
        "revoked_sessions": "2",
    }
    assert recovered_password not in str(event)


def test_password_recovery_plan_repr_omits_credential_hashes(tmp_path: Path):
    database_path = tmp_path / "recovery-plan-repr.db"
    with TestClient(create_app(database_path)) as client:
        bootstrap(client)

    plan = AuthService(Database(database_path)).prepare_password_recovery(
        username="alice",
        operator="local-host-owner",
        reason="Verify that recovery plans stay out of diagnostic output",
        new_password="temporary replacement correct horse battery staple",
    )
    rendered = repr(plan)

    assert plan.expected_password_hash not in rendered
    assert plan.new_password_hash not in rendered


def test_recover_password_help_has_no_plaintext_password_argument():
    help_text = build_parser().format_help()

    assert "recover-password" in help_text
    recovery_parser = build_parser()._subparsers._group_actions[0].choices[
        "recover-password"
    ]
    recovery_help = recovery_parser.format_help()
    assert "--password-env" in recovery_help
    assert "--password " not in recovery_help


def test_offline_password_recovery_rejects_an_unknown_target_without_backup(
    tmp_path: Path, monkeypatch, capsys
):
    database_path = tmp_path / "unknown-recovery.db"
    with TestClient(create_app(database_path)) as client:
        bootstrap(client)
    before = database_path.read_bytes()
    monkeypatch.setenv(
        "TEST_UNKNOWN_RECOVERY_PASSWORD",
        "temporary unknown correct horse battery staple",
    )

    result = main(
        [
            "--database",
            str(database_path),
            "recover-password",
            "--username",
            "missing-user",
            "--operator",
            "local-host-owner",
            "--reason",
            "Attempt a recovery for an unknown local identity",
            "--password-env",
            "TEST_UNKNOWN_RECOVERY_PASSWORD",
        ]
    )

    assert result == 2
    assert "Password recovery failed" in capsys.readouterr().err
    assert database_path.read_bytes() == before
    assert not list(tmp_path.glob("unknown-recovery.pre-password-recovery-*.db"))
