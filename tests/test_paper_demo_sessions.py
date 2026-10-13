import base64
import json
import zlib

from fastapi.testclient import TestClient

from tests.test_paper_demo import demo, IDENTITY


def test_demo_round_trip_survives_different_server_instances_without_sharing_data(tmp_path):
    first = TestClient(demo(tmp_path / "a"))
    second = TestClient(demo(tmp_path / "b"))
    auth = first.post("/api/auth/login", json={"username":IDENTITY.username, "password":IDENTITY.password}).json()
    headers = {"X-CSRF-Token": auth["csrf_token"]}
    second.cookies.update(first.cookies)
    snapshot = None
    def dispatch(client, path, method="GET", body=None):
        nonlocal snapshot
        response = client.post("/api/paper-demo/dispatch", headers=headers,
            json={"path":path, "method":method, "body":body, "snapshot":snapshot})
        assert response.status_code == 200, response.text
        snapshot = response.json()["snapshot"]
        return response.json()["result"]
    project = dispatch(first, "/api/projects")[0]
    assert first.get("/api/projects").status_code == 409
    review = dispatch(second, f"/api/projects/{project['id']}/reviews")[0]
    saved = dispatch(first, f"/api/reviews/{review['id']}/commitments", "POST", {
        "expected_revision":review["revision"], "actor":IDENTITY.actor,
        "request":"Keep private fields out of public exports.", "title":"Public-field allowlist",
        "statement":"Export only participant_id and affiliation.", "reason":"Protect private participant data.",
        "verification":"Check exact CSV headers and absence of private values.", "category":"behavior", "paths":["export.py"]})
    observed = dispatch(second, f"/api/reviews/{review['id']}")
    assert observed == saved and len(observed["commitment_changes"]) == 1
    exported = dispatch(second, f"/api/reviews/{review['id']}/export")
    assert exported["review"]["commitment_changes"] == saved["commitment_changes"]
    assert not first.app.state.database.get_review(review["id"]).commitment_changes
    envelope = json.loads(zlib.decompress(base64.urlsafe_b64decode(snapshot.split(".")[0])))
    assert not any(name.startswith("auth") for name in envelope["tables"])
    assert IDENTITY.password not in json.dumps(envelope)
    for path, body in [("/api/projects", {"name":"Other", "repo_path":"/tmp"}),
                       (f"/api/reviews/{review['id']}/tests", {"test_command":["python3", "-c", "print('no')"]})]:
        blocked = second.post("/api/paper-demo/dispatch", headers=headers,
            json={"path":path, "method":"POST", "body":body, "snapshot":snapshot})
        assert blocked.status_code == 403
        assert "snapshot" in blocked.json()
    tampered = snapshot[:-1] + ("a" if snapshot[-1] != "a" else "b")
    assert first.post("/api/paper-demo/dispatch",headers=headers,json={"path":"/api/projects","snapshot":tampered}).status_code == 409
    assert first.post("/api/paper-demo/dispatch",json={"path":"/api/projects","snapshot":snapshot}).status_code == 403
    other = first.post("/api/auth/login",json={"username":IDENTITY.username,"password":IDENTITY.password}).json()
    assert first.post("/api/paper-demo/dispatch",headers={"X-CSRF-Token":other["csrf_token"]},
        json={"path":"/api/projects","snapshot":snapshot}).status_code == 409
    assert first.post("/api/paper-demo/dispatch",headers={"X-CSRF-Token":other["csrf_token"]},
        json={"path":"https://example.com/","snapshot":None}).status_code == 422
