from __future__ import annotations

import json
import os
import subprocess
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from system.services.database import Database
from system.web.app import create_app
from tests.test_auth import ADMIN_PASSWORD, bootstrap, csrf_headers


class _QuietHandler:
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        del format, args


@contextmanager
def _serve(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@contextmanager
def _serve_git_repository(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    _git(source, "init")
    _git(source, "branch", "-M", "master")
    _git(source, "config", "user.name", "GitHub integration test")
    _git(source, "config", "user.email", "github-integration@example.test")
    (source / "README.md").write_text("# Governed repository\n", encoding="utf-8")
    (source / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(source, "add", "README.md", "app.py")
    _git(source, "commit", "-m", "Initial governed state")
    commit = _git(source, "rev-parse", "HEAD")

    web_root = tmp_path / "git-http"
    web_root.mkdir()
    bare = web_root / "governed-repo.git"
    subprocess.run(
        ["git", "clone", "--bare", str(source), str(bare)],
        check=True,
        capture_output=True,
        text=True,
    )
    _git(bare, "update-server-info")

    class Handler(_QuietHandler, SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(web_root), **kwargs)

    with _serve(Handler) as origin:
        yield f"{origin}/governed-repo.git", commit


@contextmanager
def _serve_git_repository_with_pull(tmp_path: Path):
    source = tmp_path / "pull-source"
    source.mkdir()
    _git(source, "init")
    _git(source, "branch", "-M", "master")
    _git(source, "config", "user.name", "GitHub pull request test")
    _git(source, "config", "user.email", "github-pull@example.test")
    (source / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(source, "add", "app.py")
    _git(source, "commit", "-m", "Base state")
    base = _git(source, "rev-parse", "HEAD")
    _git(source, "checkout", "-b", "agent/improve-value")
    (source / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
    (source / "test_app.py").write_text(
        "from app import VALUE\n\n\ndef test_value():\n    assert VALUE == 2\n",
        encoding="utf-8",
    )
    _git(source, "add", "app.py", "test_app.py")
    _git(source, "commit", "-m", "Improve the value")
    head = _git(source, "rev-parse", "HEAD")
    _git(source, "checkout", "master")

    web_root = tmp_path / "pull-git-http"
    web_root.mkdir()
    bare = web_root / "governed-repo.git"
    subprocess.run(
        ["git", "clone", "--bare", str(source), str(bare)],
        check=True,
        capture_output=True,
        text=True,
    )
    _git(bare, "update-ref", "refs/pull/42/head", head)
    _git(bare, "update-server-info")

    class Handler(_QuietHandler, SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(web_root), **kwargs)

    with _serve(Handler) as origin:
        yield f"{origin}/governed-repo.git", base, head


def _github_handler(state: dict):
    class Handler(_QuietHandler, BaseHTTPRequestHandler):
        def _json(self, status: int, payload: dict | list) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            form = parse_qs(self.rfile.read(length).decode())
            if self.path == "/api/app-manifests/manifest-code/conversions":
                state.setdefault("manifest_conversion_requests", []).append(form)
                self._json(
                    201,
                    {
                        "id": 271828,
                        "slug": "agentic-consensus-generated",
                        "name": "AgenticConsensus local",
                        "html_url": "https://github.com/apps/agentic-consensus-generated",
                        "client_id": "manifest-client-id",
                        "client_secret": "manifest-client-secret",
                        "webhook_secret": "discarded-webhook-secret",
                        "pem": "discarded-private-key",
                        "permissions": {
                            "metadata": "read",
                            "contents": "read",
                            "pull_requests": "read",
                        },
                        "events": [],
                    },
                )
                return
            if self.path == "/login/oauth/access_token":
                state["token_requests"].append(form)
                if form.get("grant_type") == ["refresh_token"]:
                    self._json(
                        200,
                        {
                            "access_token": "ghu_refreshed_secret",
                            "expires_in": 28_800,
                            "refresh_token": "ghr_rotated_secret",
                            "refresh_token_expires_in": 15_897_600,
                            "token_type": "bearer",
                            "scope": "",
                        },
                    )
                else:
                    self._json(
                        200,
                        {
                            "access_token": state.get("access_token", "ghu_original_secret"),
                            "expires_in": state.get("expires_in", 28_800),
                            "refresh_token": "ghr_original_secret",
                            "refresh_token_expires_in": 15_897_600,
                            "token_type": "bearer",
                            "scope": "",
                        },
                    )
                return
            self._json(404, {"message": "not found"})

        def do_GET(self):  # noqa: N802
            state["requests"].append((self.path, self.headers.get("Authorization")))
            if self.path == "/api/user":
                self._json(
                    200,
                    {
                        "id": 314159,
                        "login": "researcher",
                        "html_url": "https://github.com/researcher",
                    },
                )
                return
            if self.path.startswith("/api/user/installations?"):
                installations = state.get(
                    "installations",
                    [
                        {
                            "id": 42,
                            "account": {
                                "id": 314159,
                                "login": "researcher",
                                "type": "User",
                            },
                            "repository_selection": "selected",
                            "permissions": {"metadata": "read", "contents": "read"},
                        }
                    ],
                )
                self._json(
                    200,
                    {
                        "total_count": len(installations),
                        "installations": installations,
                    },
                )
                return
            if self.path.startswith("/api/user/installations/42/repositories?"):
                self._json(
                    200,
                    {
                        "total_count": 1,
                        "repositories": [
                            {
                                "id": 9001,
                                "name": "governed-repo",
                                "full_name": "researcher/governed-repo",
                                "private": True,
                                "visibility": "private",
                                "description": "A real repository selected for governance.",
                                "html_url": "https://github.com/researcher/governed-repo",
                                "clone_url": state["clone_url"],
                                "default_branch": "master",
                                "archived": False,
                                "disabled": False,
                                "updated_at": "2026-08-30T08:00:00Z",
                                "permissions": {"admin": True, "push": True, "pull": True},
                            }
                        ],
                    },
                )
                return
            if self.path.startswith("/api/repos/researcher/governed-repo/pulls?"):
                pull = state.get("pull")
                self._json(200, [pull] if pull else [])
                return
            if self.path == "/api/repos/researcher/governed-repo/pulls/42":
                pull = state.get("pull")
                self._json(200 if pull else 404, pull or {"message": "not found"})
                return
            self._json(404, {"message": "not found"})

        def do_DELETE(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode() if length else ""
            state["delete_requests"].append((self.path, self.headers.get("Authorization"), body))
            if self.path == "/api/applications/test-client-id/token":
                delete_status = state.get("delete_status", 204)
                if delete_status == 204:
                    self.send_response(delete_status)
                    self.end_headers()
                else:
                    self._json(delete_status, {"message": "revocation unavailable"})
                return
            self._json(404, {"message": "not found"})

    return Handler


def _configure_github(monkeypatch, base_url: str, managed_repos: Path) -> None:
    monkeypatch.setenv("GITHUB_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv("GITHUB_APP_SLUG", "agentic-consensus-test")
    monkeypatch.setenv("GITHUB_AUTHORIZE_URL", f"{base_url}/login/oauth/authorize")
    monkeypatch.setenv("GITHUB_TOKEN_URL", f"{base_url}/login/oauth/access_token")
    monkeypatch.setenv("GITHUB_API_URL", f"{base_url}/api")
    monkeypatch.setenv("CONSENSUS_GITHUB_REPOSITORIES_DIR", str(managed_repos))


def _configure_manifest_endpoints(monkeypatch, base_url: str, managed_repos: Path) -> None:
    for name in ("GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET", "GITHUB_APP_SLUG"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GITHUB_WEB_URL", base_url)
    monkeypatch.setenv("GITHUB_MANIFEST_URL", f"{base_url}/settings/apps/new")
    monkeypatch.setenv("GITHUB_AUTHORIZE_URL", f"{base_url}/login/oauth/authorize")
    monkeypatch.setenv("GITHUB_TOKEN_URL", f"{base_url}/login/oauth/access_token")
    monkeypatch.setenv("GITHUB_API_URL", f"{base_url}/api")
    monkeypatch.setenv("CONSENSUS_GITHUB_REPOSITORIES_DIR", str(managed_repos))


def _begin_and_complete_connection(client: TestClient, auth: dict) -> dict:
    started = client.post(
        "/api/github/oauth/start",
        headers=csrf_headers(auth),
        json={"redirect_uri": "http://127.0.0.1:8765/api/github/oauth/callback"},
    )
    assert started.status_code == 200, started.text
    payload = started.json()
    query = parse_qs(urlparse(payload["authorization_url"]).query)
    assert query["client_id"] == ["test-client-id"]
    assert query["redirect_uri"] == ["http://127.0.0.1:8765/api/github/oauth/callback"]
    assert query["code_challenge_method"] == ["S256"]
    assert len(query["code_challenge"][0]) == 43
    assert len(query["state"][0]) >= 40

    callback = client.get(
        "/api/github/oauth/callback",
        params={"code": "one-time-code", "state": query["state"][0]},
        follow_redirects=False,
    )
    assert callback.status_code == 303, callback.text
    assert callback.headers["location"] == "/?github=connected"
    return {"started": payload, "state": query["state"][0]}


def test_github_status_offers_browser_setup_instead_of_environment_variables(
    tmp_path: Path, monkeypatch
):
    for name in (
        "GITHUB_CLIENT_ID",
        "GITHUB_CLIENT_SECRET",
        "GITHUB_APP_SLUG",
        "GITHUB_AUTHORIZE_URL",
        "GITHUB_TOKEN_URL",
        "GITHUB_API_URL",
    ):
        monkeypatch.delenv(name, raising=False)

    with TestClient(create_app(tmp_path / "unconfigured.db")) as client:
        auth = bootstrap(client)
        status = client.get("/api/github/status")
        assert status.status_code == 200
        assert status.json() == {
            "configured": False,
            "setup_required": True,
            "setup_allowed": True,
            "connection_allowed": True,
            "connected": False,
            "login": None,
            "github_user_id": None,
            "connected_at": None,
            "token_expires_at": None,
            "install_url": None,
        }
        start = client.post(
            "/api/github/oauth/start",
            headers=csrf_headers(auth),
            json={"redirect_uri": "http://127.0.0.1:8765/api/github/oauth/callback"},
        )
        assert start.status_code == 503
        assert start.json()["detail"] == "Connect GitHub to finish the one-time setup"


def test_admin_can_create_the_read_only_github_app_in_browser_then_continue_oauth(
    tmp_path: Path, monkeypatch
):
    github_state = {
        "clone_url": "https://github.com/researcher/governed-repo.git",
        "requests": [],
        "token_requests": [],
        "delete_requests": [],
        "manifest_conversion_requests": [],
    }
    with _serve(_github_handler(github_state)) as github_url:
        _configure_manifest_endpoints(monkeypatch, github_url, tmp_path / "managed")
        hosted_origin = "https://control.example.test"
        monkeypatch.setenv("VERCEL_URL", "control.example.test")
        database_path = tmp_path / "manifest.db"
        with TestClient(create_app(database_path)) as client:
            auth = bootstrap(client)
            started = client.post(
                "/api/github/app/setup/start",
                headers=csrf_headers(auth),
                json={"origin": hosted_origin},
            )
            assert started.status_code == 200, started.text
            setup = started.json()
            registration = urlparse(setup["registration_url"])
            assert registration.path == "/settings/apps/new"
            manifest_state = parse_qs(registration.query)["state"][0]
            assert len(manifest_state) >= 40
            manifest = setup["manifest"]
            assert manifest["callback_urls"] == [
                f"{hosted_origin}/api/github/oauth/callback"
            ]
            assert manifest["redirect_url"] == (
                f"{hosted_origin}/api/github/app/setup/callback"
            )
            assert manifest["setup_url"] == f"{hosted_origin}/?github=installed"
            assert manifest["default_permissions"] == {
                "metadata": "read",
                "contents": "read",
                "pull_requests": "read",
            }
            assert manifest["default_events"] == []
            assert manifest["public"] is True
            assert "hook_attributes" not in manifest
            assert manifest["request_oauth_on_install"] is False

            raw_before_callback = database_path.read_bytes()
            assert manifest_state.encode() not in raw_before_callback

            client.cookies.clear()
            configured = client.get(
                "/api/github/app/setup/callback",
                params={"code": "manifest-code", "state": manifest_state},
                follow_redirects=False,
            )
            assert configured.status_code == 303, configured.text
            authorization = urlparse(configured.headers["location"])
            assert authorization.path == "/login/oauth/authorize"
            oauth_query = parse_qs(authorization.query)
            assert oauth_query["client_id"] == ["manifest-client-id"]
            assert oauth_query["redirect_uri"] == [
                f"{hosted_origin}/api/github/oauth/callback"
            ]
            assert oauth_query["code_challenge_method"] == ["S256"]

            replay = client.get(
                "/api/github/app/setup/callback",
                params={"code": "manifest-code", "state": manifest_state},
                follow_redirects=False,
            )
            assert replay.status_code == 400
            assert replay.json()["detail"] == (
                "GitHub App setup state is invalid or expired"
            )

            oauth_callback = client.get(
                "/api/github/oauth/callback",
                params={"code": "oauth-code", "state": oauth_query["state"][0]},
                follow_redirects=False,
            )
            assert oauth_callback.status_code == 303, oauth_callback.text
            assert oauth_callback.headers["location"] == "/?github=connected"

            login = client.post(
                "/api/auth/login",
                json={"username": "alice", "password": ADMIN_PASSWORD},
            )
            assert login.status_code == 200
            status = client.get("/api/github/status").json()
            assert status["configured"] is True
            assert status["setup_required"] is False
            assert status["connected"] is True
            assert status["login"] == "researcher"
            assert status["install_url"] == (
                f"{github_url}/apps/agentic-consensus-generated/installations/new"
            )

            raw_database = database_path.read_bytes()
            for secret in (
                b"manifest-client-secret",
                b"discarded-webhook-secret",
                b"discarded-private-key",
                b"ghu_original_secret",
                b"ghr_original_secret",
                manifest_state.encode(),
            ):
                assert secret not in raw_database

            backup_path = tmp_path / "manifest-backup.db"
            manifest_report = Database(database_path).backup(backup_path)
            assert Database.validate_backup(backup_path) == manifest_report
            assert b"manifest-client-secret" not in backup_path.read_bytes()

        with TestClient(create_app(database_path)) as restarted:
            login = restarted.post(
                "/api/auth/login",
                json={"username": "alice", "password": ADMIN_PASSWORD},
            )
            assert login.status_code == 200
            restarted_status = restarted.get("/api/github/status").json()
            assert restarted_status["configured"] is True
            assert restarted_status["connected"] is True
            assert restarted_status["login"] == "researcher"


def test_hosted_github_setup_rejects_an_unconfigured_origin(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("VERCEL_URL", "control.example.test")

    with TestClient(create_app(tmp_path / "hosted-origin.db")) as client:
        auth = bootstrap(client)
        response = client.post(
            "/api/github/app/setup/start",
            headers=csrf_headers(auth),
            json={"origin": "https://attacker.example.test"},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "GitHub setup origin is not allowed"


def test_oauth_sends_the_user_to_repository_installation_when_none_exists(
    tmp_path: Path, monkeypatch
):
    github_state = {
        "clone_url": "https://github.com/researcher/governed-repo.git",
        "requests": [],
        "token_requests": [],
        "delete_requests": [],
        "installations": [],
    }
    with _serve(_github_handler(github_state)) as github_url:
        _configure_github(monkeypatch, github_url, tmp_path / "managed")
        with TestClient(create_app(tmp_path / "install.db")) as client:
            auth = bootstrap(client)
            started = client.post(
                "/api/github/oauth/start",
                headers=csrf_headers(auth),
                json={
                    "redirect_uri": "http://127.0.0.1:8765/api/github/oauth/callback"
                },
            ).json()
            oauth_state = parse_qs(urlparse(started["authorization_url"]).query)["state"][0]
            callback = client.get(
                "/api/github/oauth/callback",
                params={"code": "oauth-code", "state": oauth_state},
                follow_redirects=False,
            )
            assert callback.status_code == 303
            assert callback.headers["location"] == (
                f"{github_url}/apps/agentic-consensus-test/installations/new"
            )


def test_oauth_connection_uses_pkce_one_time_state_and_encrypted_tokens(
    tmp_path: Path, monkeypatch
):
    github_state = {
        "clone_url": "https://github.com/researcher/governed-repo.git",
        "requests": [],
        "token_requests": [],
        "delete_requests": [],
    }
    with _serve(_github_handler(github_state)) as github_url:
        _configure_github(monkeypatch, github_url, tmp_path / "managed")
        database_path = tmp_path / "oauth.db"
        with TestClient(create_app(database_path)) as client:
            auth = bootstrap(client)
            flow = _begin_and_complete_connection(client, auth)

            replay = client.get(
                "/api/github/oauth/callback",
                params={"code": "replayed-code", "state": flow["state"]},
                follow_redirects=False,
            )
            assert replay.status_code == 400
            assert replay.json()["detail"] == "GitHub authorization state is invalid or expired"

            status = client.get("/api/github/status").json()
            assert status["configured"] is True
            assert status["connected"] is True
            assert status["login"] == "researcher"
            assert status["github_user_id"] == 314159
            assert status["install_url"] == (
                f"{github_url}/apps/agentic-consensus-test/installations/new"
            )

            repositories = client.get("/api/github/repositories")
            assert repositories.status_code == 200, repositories.text
            assert repositories.json() == [
                {
                    "id": 9001,
                    "installation_id": 42,
                    "name": "governed-repo",
                    "full_name": "researcher/governed-repo",
                    "private": True,
                    "visibility": "private",
                    "description": "A real repository selected for governance.",
                    "html_url": "https://github.com/researcher/governed-repo",
                    "default_branch": "master",
                    "archived": False,
                    "updated_at": "2026-08-30T08:00:00Z",
                    "permissions": {"admin": True, "push": True, "pull": True},
                }
            ]

            raw_database = database_path.read_bytes()
            for secret in (
                b"ghu_original_secret",
                b"ghr_original_secret",
                flow["state"].encode(),
                b"one-time-code",
                b"test-client-secret",
            ):
                assert secret not in raw_database

            backup_path = tmp_path / "oauth-backup.db"
            manifest = Database(database_path).backup(backup_path)
            assert manifest["health"]["projects"] == 0
            assert Database.validate_backup(backup_path) == manifest
            backup_bytes = backup_path.read_bytes()
            assert b"ghu_original_secret" not in backup_bytes
            assert b"ghr_original_secret" not in backup_bytes

            disconnected = client.delete(
                "/api/github/connection", headers=csrf_headers(auth)
            )
            assert disconnected.status_code == 200
            assert disconnected.json() == {
                "disconnected": True,
                "remote_token_revoked": True,
            }
            assert client.get("/api/github/status").json()["connected"] is False
            assert github_state["delete_requests"][0][0] == (
                "/api/applications/test-client-id/token"
            )
            assert json.loads(github_state["delete_requests"][0][2]) == {
                "access_token": "ghu_original_secret"
            }


def test_oauth_callback_is_state_bound_and_does_not_require_the_local_session_cookie(
    tmp_path: Path, monkeypatch
):
    github_state = {
        "clone_url": "https://github.com/researcher/governed-repo.git",
        "requests": [],
        "token_requests": [],
        "delete_requests": [],
    }
    with _serve(_github_handler(github_state)) as github_url:
        _configure_github(monkeypatch, github_url, tmp_path / "managed")
        with TestClient(create_app(tmp_path / "callback.db")) as client:
            auth = bootstrap(client)
            started = client.post(
                "/api/github/oauth/start",
                headers=csrf_headers(auth),
                json={
                    "redirect_uri": "http://127.0.0.1:8765/api/github/oauth/callback"
                },
            ).json()
            oauth_state = parse_qs(urlparse(started["authorization_url"]).query)["state"][0]
            client.cookies.clear()

            callback = client.get(
                "/api/github/oauth/callback",
                params={"code": "cross-site-code", "state": oauth_state},
                follow_redirects=False,
            )
            assert callback.status_code == 303
            assert client.get("/api/github/status").status_code == 401

            login = client.post(
                "/api/auth/login",
                json={"username": "alice", "password": ADMIN_PASSWORD},
            )
            assert login.status_code == 200
            assert client.get("/api/github/status").json()["login"] == "researcher"


def test_selected_github_repository_is_cloned_registered_and_governed_locally(
    tmp_path: Path, monkeypatch
):
    with _serve_git_repository(tmp_path) as (clone_url, expected_head):
        github_state = {
            "clone_url": clone_url,
            "requests": [],
            "token_requests": [],
            "delete_requests": [],
        }
        with _serve(_github_handler(github_state)) as github_url:
            managed = tmp_path / "managed-repositories"
            _configure_github(monkeypatch, github_url, managed)
            database_path = tmp_path / "import.db"
            with TestClient(create_app(database_path)) as client:
                auth = bootstrap(client)
                _begin_and_complete_connection(client, auth)
                imported = client.post(
                    "/api/github/repositories/9001/import",
                    headers=csrf_headers(auth),
                    json={
                        "installation_id": 42,
                        "name": "Governed GitHub repository",
                        "test_command": ["python3", "-m", "unittest", "-q"],
                        "claims": [],
                        "policy_id": "github-readonly/v1",
                        "default_authority": "repository owner",
                        "authority_grants": [
                            {
                                "authority": "repository owner",
                                "actors": ["alice@example.test"],
                                "actions": ["commit", "waive", "rebase", "reject"],
                            }
                        ],
                    },
                )
                assert imported.status_code == 201, imported.text
                project = imported.json()
                assert project["name"] == "Governed GitHub repository"
                assert project["head_ref"] == expected_head
                assert project["repo_label"] == "github://researcher/governed-repo"
                assert project["source"] == {
                    "provider": "github",
                    "repository_id": 9001,
                    "installation_id": 42,
                    "full_name": "researcher/governed-repo",
                    "html_url": "https://github.com/researcher/governed-repo",
                    "default_branch": "master",
                    "visibility": "private",
                    "connected_by": "alice@example.test",
                    "imported_at": project["source"]["imported_at"],
                }

                checkout = Path(project["repo_path"])
                assert checkout.is_relative_to(managed.resolve())
                assert (checkout / ".git").is_dir()
                assert (checkout / "README.md").read_text(encoding="utf-8") == (
                    "# Governed repository\n"
                )
                assert _git(checkout, "remote", "get-url", "origin") == clone_url
                assert "ghu_original_secret" not in (checkout / ".git/config").read_text()
                assert _git(checkout, "status", "--short") == ""

                duplicate = client.post(
                    "/api/github/repositories/9001/import",
                    headers=csrf_headers(auth),
                    json={"installation_id": 42, "name": "Duplicate", "claims": []},
                )
                assert duplicate.status_code == 409
                assert "already managed" in duplicate.json()["detail"]
                assert len(list(managed.glob("*"))) == 1

                disconnected = client.delete(
                    "/api/github/connection", headers=csrf_headers(auth)
                )
                assert disconnected.status_code == 200
                assert disconnected.json()["remote_token_revoked"] is True
                assert checkout.is_dir()
                assert project["id"] in {
                    item["id"] for item in client.get("/api/projects").json()
                }

            saved = Database(database_path).get_project(project["id"])
            assert saved.source is not None
            assert saved.source.full_name == "researcher/governed-repo"


def test_open_pull_request_can_be_selected_and_analyzed_in_one_step(
    tmp_path: Path, monkeypatch
):
    with _serve_git_repository_with_pull(tmp_path) as (clone_url, base, head):
        pull = {
            "number": 42,
            "title": "Improve the governed value",
            "html_url": "https://github.com/researcher/governed-repo/pull/42",
            "state": "open",
            "draft": False,
            "user": {"login": "researcher"},
            "base": {"ref": "master", "sha": base},
            "head": {"ref": "agent/improve-value", "sha": head},
            "updated_at": "2026-09-01T08:00:00Z",
        }
        github_state = {
            "clone_url": clone_url,
            "pull": pull,
            "requests": [],
            "token_requests": [],
            "delete_requests": [],
        }
        with _serve(_github_handler(github_state)) as github_url:
            managed = tmp_path / "managed-pull-repositories"
            _configure_github(monkeypatch, github_url, managed)
            with TestClient(create_app(tmp_path / "pull-analysis.db")) as client:
                auth = bootstrap(client)
                _begin_and_complete_connection(client, auth)

                pulls = client.get(
                    "/api/github/repositories/9001/pulls",
                    params={"installation_id": 42},
                )
                assert pulls.status_code == 200, pulls.text
                assert pulls.json() == [
                    {
                        "number": 42,
                        "title": "Improve the governed value",
                        "html_url": "https://github.com/researcher/governed-repo/pull/42",
                        "draft": False,
                        "author": "researcher",
                        "base_ref": "master",
                        "base_sha": base,
                        "head_ref": "agent/improve-value",
                        "head_sha": head,
                        "updated_at": "2026-09-01T08:00:00Z",
                    }
                ]

                analyzed = client.post(
                    "/api/github/repositories/9001/pulls/42/analyze",
                    headers=csrf_headers(auth),
                    json={
                        "installation_id": 42,
                        "name": "governed-repo",
                        "test_command": [],
                        "claims": [],
                        "policy_id": "github-readonly/v1",
                        "default_authority": "repository owner",
                        "authority_grants": [
                            {
                                "authority": "repository owner",
                                "actors": ["alice@example.test"],
                                "actions": ["commit", "waive", "rebase", "reject"],
                            }
                        ],
                    },
                )
                assert analyzed.status_code == 201, analyzed.text
                result = analyzed.json()
                assert result["project_created"] is True
                assert result["review_reused"] is False
                assert result["pull_request"]["number"] == 42
                assert result["review"]["base_ref"] == base
                assert result["review"]["target_ref"] == head
                assert result["review"]["intent_summary"] == pull["title"]
                assert result["review"]["proposer"] == "github:@researcher"
                assert result["review"]["external_url"] == pull["html_url"]
                assert result["review"]["external_label"] == "GitHub PR #42"
                assert result["review"]["changed_paths"] == ["app.py", "test_app.py"]

                checkout = Path(result["project"]["repo_path"])
                assert _git(
                    checkout,
                    "rev-parse",
                    "refs/agentic-consensus/github/pr-42/head",
                ) == head
                assert "ghu_original_secret" not in (
                    checkout / ".git/config"
                ).read_text(encoding="utf-8")

                repeated = client.post(
                    "/api/github/repositories/9001/pulls/42/analyze",
                    headers=csrf_headers(auth),
                    json={
                        "installation_id": 42,
                        "name": "ignored-for-managed-repository",
                        "claims": [],
                    },
                )
                assert repeated.status_code == 200, repeated.text
                assert repeated.json()["project_created"] is False
                assert repeated.json()["review_reused"] is True
                assert repeated.json()["review"]["id"] == result["review"]["id"]


def test_draft_pull_request_cannot_be_presented_as_merge_ready(tmp_path: Path, monkeypatch):
    with _serve_git_repository_with_pull(tmp_path) as (clone_url, base, head):
        github_state = {
            "clone_url": clone_url,
            "pull": {
                "number": 42,
                "title": "Work in progress",
                "html_url": "https://github.com/researcher/governed-repo/pull/42",
                "state": "open",
                "draft": True,
                "user": {"login": "researcher"},
                "base": {"ref": "master", "sha": base},
                "head": {"ref": "agent/improve-value", "sha": head},
                "updated_at": "2026-09-01T08:00:00Z",
            },
            "requests": [],
            "token_requests": [],
            "delete_requests": [],
        }
        with _serve(_github_handler(github_state)) as github_url:
            managed = tmp_path / "managed-draft-repositories"
            _configure_github(monkeypatch, github_url, managed)
            with TestClient(create_app(tmp_path / "draft-analysis.db")) as client:
                auth = bootstrap(client)
                _begin_and_complete_connection(client, auth)
                response = client.post(
                    "/api/github/repositories/9001/pulls/42/analyze",
                    headers=csrf_headers(auth),
                    json={"installation_id": 42, "name": "governed-repo"},
                )

                assert response.status_code == 422
                assert response.json()["detail"] == (
                    "GitHub pull request is still a draft; mark it ready for review and retry"
                )
                assert client.get("/api/projects").json() == []
                assert not managed.exists() or list(managed.iterdir()) == []


def test_disconnect_reports_remote_revocation_failure_but_clears_local_credentials(
    tmp_path: Path, monkeypatch
):
    github_state = {
        "clone_url": "https://github.com/researcher/governed-repo.git",
        "requests": [],
        "token_requests": [],
        "delete_requests": [],
        "delete_status": 503,
    }
    with _serve(_github_handler(github_state)) as github_url:
        _configure_github(monkeypatch, github_url, tmp_path / "managed")
        with TestClient(create_app(tmp_path / "disconnect.db")) as client:
            auth = bootstrap(client)
            _begin_and_complete_connection(client, auth)

            disconnected = client.delete(
                "/api/github/connection", headers=csrf_headers(auth)
            )
            assert disconnected.status_code == 200
            assert disconnected.json() == {
                "disconnected": True,
                "remote_token_revoked": False,
            }
            assert client.get("/api/github/status").json()["connected"] is False


def test_expired_user_token_is_rotated_before_repository_access(tmp_path: Path, monkeypatch):
    github_state = {
        "clone_url": "https://github.com/researcher/governed-repo.git",
        "access_token": "ghu_expiring_secret",
        "expires_in": 1,
        "requests": [],
        "token_requests": [],
        "delete_requests": [],
    }
    with _serve(_github_handler(github_state)) as github_url:
        _configure_github(monkeypatch, github_url, tmp_path / "managed")
        database_path = tmp_path / "refresh.db"
        with TestClient(create_app(database_path)) as client:
            auth = bootstrap(client)
            _begin_and_complete_connection(client, auth)
            response = client.get("/api/github/repositories")
            assert response.status_code == 200, response.text

        assert any(
            request.get("grant_type") == ["refresh_token"]
            and request.get("refresh_token") == ["ghr_original_secret"]
            for request in github_state["token_requests"]
        )
        repository_requests = [
            item for item in github_state["requests"] if "repositories" in item[0]
        ]
        assert repository_requests[-1][1] == "Bearer ghu_refreshed_secret"
        raw_database = database_path.read_bytes()
        for secret in (
            b"ghu_expiring_secret",
            b"ghu_refreshed_secret",
            b"ghr_original_secret",
            b"ghr_rotated_secret",
        ):
            assert secret not in raw_database


def test_import_rejects_clone_host_redirects_before_git_receives_a_token(
    tmp_path: Path, monkeypatch
):
    github_state = {
        "clone_url": "https://credential-collector.example/repository.git",
        "requests": [],
        "token_requests": [],
        "delete_requests": [],
    }
    with _serve(_github_handler(github_state)) as github_url:
        managed = tmp_path / "managed"
        _configure_github(monkeypatch, github_url, managed)
        with TestClient(create_app(tmp_path / "clone-host.db")) as client:
            auth = bootstrap(client)
            _begin_and_complete_connection(client, auth)
            response = client.post(
                "/api/github/repositories/9001/import",
                headers=csrf_headers(auth),
                json={"installation_id": 42, "name": "Unsafe", "claims": []},
            )
            assert response.status_code == 422
            assert response.json()["detail"] == (
                "GitHub clone URL must be credential-free HTTPS"
            )
            assert not managed.exists() or list(managed.iterdir()) == []


def test_github_mutations_require_csrf_and_operator_role(tmp_path: Path, monkeypatch):
    github_state = {
        "clone_url": "https://github.com/researcher/governed-repo.git",
        "requests": [],
        "token_requests": [],
        "delete_requests": [],
    }
    with _serve(_github_handler(github_state)) as github_url:
        _configure_github(monkeypatch, github_url, tmp_path / "managed")
        with TestClient(create_app(tmp_path / "roles.db")) as client:
            admin = bootstrap(client)
            assert client.post("/api/github/oauth/start", json={}).status_code == 403
            assert client.post(
                "/api/github/app/setup/start",
                json={"origin": "http://127.0.0.1:8765"},
            ).status_code == 403
            assert client.post(
                "/api/github/repositories/9001/pulls/42/analyze",
                json={"installation_id": 42, "name": "Unauthorized PR"},
            ).status_code == 403
            viewer = client.post(
                "/api/users",
                headers=csrf_headers(admin),
                json={
                    "username": "viewer",
                    "actor": "viewer@example.test",
                    "password": "viewer temporary correct horse battery staple",
                    "role": "viewer",
                },
            ).json()
            client.post("/api/auth/logout", headers=csrf_headers(admin))
            viewer_auth = client.post(
                "/api/auth/login",
                json={
                    "username": viewer["username"],
                    "password": "viewer temporary correct horse battery staple",
                },
            ).json()
            viewer_auth = client.post(
                "/api/auth/password",
                headers=csrf_headers(viewer_auth),
                json={
                    "current_password": "viewer temporary correct horse battery staple",
                    "new_password": "viewer permanent correct horse battery staple",
                },
            ).json()
            denied = client.post(
                "/api/github/oauth/start",
                headers=csrf_headers(viewer_auth),
                json={"redirect_uri": "http://127.0.0.1:8765/api/github/oauth/callback"},
            )
            assert denied.status_code == 403
            assert denied.json()["detail"] == "operator role required"
            setup_denied = client.post(
                "/api/github/app/setup/start",
                headers=csrf_headers(viewer_auth),
                json={"origin": "http://127.0.0.1:8765"},
            )
            assert setup_denied.status_code == 403
            assert setup_denied.json()["detail"] == "administrator role required"
            analyze_denied = client.post(
                "/api/github/repositories/9001/pulls/42/analyze",
                headers=csrf_headers(viewer_auth),
                json={"installation_id": 42, "name": "Viewer PR"},
            )
            assert analyze_denied.status_code == 403
            assert analyze_denied.json()["detail"] == "operator role required"
            viewer_status = client.get("/api/github/status").json()
            assert viewer_status["setup_allowed"] is False
            assert viewer_status["connection_allowed"] is False


def test_operator_console_exposes_github_connection_repository_picker_and_local_fallback(
    tmp_path: Path,
):
    with TestClient(create_app(tmp_path / "github-ui.db", require_authentication=False)) as client:
        html = client.get("/").text
        content_security_policy = client.get("/").headers["content-security-policy"]
        javascript = client.get("/static/app.js").text
        stylesheet = client.get("/static/app.css").text

        assert 'id="github-source-tab"' in html
        assert 'id="local-source-tab"' in html
        assert 'id="github-connection-status"' in html
        assert 'id="github-connect-button"' in html
        assert 'id="github-install-button"' in html
        assert 'id="github-repository-search"' in html
        assert 'id="github-repository-list"' in html
        assert 'id="github-pull-request-list"' in html
        assert "Choose an open pull request" in html
        assert 'id="github-disconnect-button"' in html
        assert 'name="repo_path"' in html
        assert "Sign in with GitHub" in html
        assert (
            'class="button button-small button-primary" id="github-connect-button"'
            in html
        )
        assert "function loadGitHubRepositories" in javascript
        assert "function loadGitHubPullRequests" in javascript
        assert "function submitGitHubAppManifest" in javascript
        assert 'api("/api/github/app/setup/start"' in javascript
        assert 'api("/api/github/oauth/start"' in javascript
        assert "`/api/github/repositories/${selected.id}/pulls/${selectedPull.number}/analyze`" in javascript
        assert 'new URLSearchParams(window.location.search).get("github")' in javascript
        assert 'addEventListener("click", () => openProject("github"))' in javascript
        assert "required_configuration" not in javascript
        assert "GITHUB_CLIENT_ID" not in javascript
        assert "to .env" not in javascript
        assert "GitHub App setup required" not in javascript
        assert "form-action 'self' https://github.com;" in content_security_policy
        assert ".repository-source-tabs" in stylesheet
        assert ".github-repository-card" in stylesheet
        assert ".source-tab { min-height:44px; }" in stylesheet
