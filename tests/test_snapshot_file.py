from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from system.web.app import create_app
from tests.helpers import commit, create_billing_repo


@pytest.fixture
def snapshot(tmp_path: Path):
    repo, _base, _target = create_billing_repo(tmp_path)
    (repo / "space 中文.txt").write_text("  preserved\n\nlast line\n", encoding="utf-8")
    (repo / "empty.txt").write_bytes(b"")
    (repo / "binary.bin").write_bytes(b"before\x00after")
    (repo / "legacy-encoding.txt").write_bytes(b"\xff\xfe\x80")
    (repo / "large.txt").write_bytes(b"x" * 262_145)
    (repo / "link.txt").symlink_to("/etc/passwd")
    revision = commit(repo, "snapshot-reader fixtures")
    (repo / "space 中文.txt").write_text("unsaved working copy", encoding="utf-8")
    (repo / "untracked.txt").write_text("workspace only", encoding="utf-8")
    with TestClient(create_app(tmp_path / "snapshot.db", require_authentication=False)) as client:
        project = client.post("/api/projects", json={
            "name": "Snapshot reader", "repo_path": str(repo), "head_ref": revision,
            "test_command": [], "claims": [],
        }).json()
        yield client, project, revision, repo


def read(snapshot, path, revision=None):
    client, project, base, _repo = snapshot
    return client.get(f"/api/projects/{project['id']}/file", params={
        "path": path, "revision": revision if revision is not None else base,
    })


def test_reader_preserves_exact_snapshot_text_and_never_reads_working_copy(snapshot):
    response = read(snapshot, "space 中文.txt")
    assert response.status_code == 200
    assert response.headers.get("cache-control") == "no-store"
    file = response.json()
    assert file["status"] == "text"
    assert file["content"] == "  preserved\n\nlast line\n"
    assert file["revision"] == snapshot[2]
    assert file["path"] == "space 中文.txt"
    assert file["project_id"] == snapshot[1]["id"]
    assert file["byte_size"] == len(file["content"].encode("utf-8"))
    assert file["byte_limit"] == 262_144
    assert len(file["object_id"]) == 40
    assert (snapshot[3] / "space 中文.txt").read_text() == "unsaved working copy"


@pytest.mark.parametrize("path,status", [
    ("empty.txt", "empty"), ("binary.bin", "binary"),
    ("legacy-encoding.txt", "binary"), ("large.txt", "too_large"),
    ("link.txt", "symlink"),
])
def test_reader_distinguishes_non_previewable_files_without_executing_or_following(snapshot, path, status):
    response = read(snapshot, path)
    assert response.status_code == 200
    file = response.json()
    assert file["status"] == status
    assert file["content"] == ("" if status == "empty" else None)
    assert "root:" not in str(file)


@pytest.mark.parametrize("path", ["../secret", "/etc/passwd", "legacy/../checkout.py", "legacy\\billing.py", "", "a\x00b", "./checkout.py"])
def test_reader_rejects_unsafe_or_ambiguous_paths(snapshot, path):
    assert read(snapshot, path).status_code == 422


@pytest.mark.parametrize("path", ["untracked.txt", "missing.py", "legacy", ".git/config", "*.py"])
def test_reader_only_admits_exact_tracked_file_paths(snapshot, path):
    assert read(snapshot, path).status_code == 404


def test_reader_cannot_select_an_arbitrary_or_changed_git_revision(snapshot):
    assert read(snapshot, "checkout.py", "HEAD").status_code == 422
    assert read(snapshot, "checkout.py", "a" * 40).status_code == 409
    client = snapshot[0]
    assert client.get("/api/projects/project-missing/file", params={"path": "checkout.py", "revision": snapshot[2]}).status_code == 404


def test_reader_requires_authentication(tmp_path):
    with TestClient(create_app(tmp_path / "secure.db")) as client:
        assert client.get("/api/projects/missing/file", params={"path": "x", "revision": "a" * 40}).status_code == 401


def test_read_only_identity_can_read_a_snapshot_without_write_authority(tmp_path):
    repo, base, _target = create_billing_repo(tmp_path)
    with TestClient(create_app(tmp_path / "viewer.db")) as client:
        admin = client.post("/api/auth/bootstrap", json={
            "username": "admin", "actor": "admin@example.test", "password": "snapshot administrator password",
        }).json()
        headers = {"X-CSRF-Token": admin["csrf_token"]}
        project = client.post("/api/projects", headers=headers, json={
            "name": "Read-only", "repo_path": str(repo), "head_ref": base, "test_command": [], "claims": [],
        }).json()
        assert client.post("/api/users", headers=headers, json={
            "username": "reader", "actor": "reader@example.test", "password": "snapshot reader initial password", "role": "viewer",
        }).status_code == 201
        client.post("/api/auth/logout", headers=headers)
        auth = client.post("/api/auth/login", json={"username": "reader", "password": "snapshot reader initial password"}).json()
        auth = client.post("/api/auth/password", headers={"X-CSRF-Token": auth["csrf_token"]}, json={
            "current_password": "snapshot reader initial password", "new_password": "snapshot reader updated password",
        }).json()
        response = client.get(f"/api/projects/{project['id']}/file", params={"path": "checkout.py", "revision": base})
        assert response.status_code == 200
        assert response.json()["content"] == "def total(value):\n    return value * 2\n"
        assert client.post("/api/projects", headers={"X-CSRF-Token": auth["csrf_token"]}, json={}).status_code == 403
