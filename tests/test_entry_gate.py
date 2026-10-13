from pathlib import Path
import re
import shutil
import subprocess

from fastapi.testclient import TestClient
import pytest

from system.web.app import create_app


def test_entry_gate_slow_start_and_recovery():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is needed for entry lifecycle tests")
    result = subprocess.run(
        [node, "--test", str(Path(__file__).with_name("entry_gate.test.cjs"))],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_entry_script_works_at_root_and_static_path_without_relaxing_csp(tmp_path: Path):
    with TestClient(create_app(tmp_path / "entry.db")) as client:
        root = client.get("/")
        assert re.search(r'<script src="\./entry\.js[^\"]*"', root.text)
        script = client.get("/entry.js")
        assert script.status_code == 200
        assert script.text == client.get("/static/entry.js").text
        assert script.headers["cache-control"] == "no-cache"
        assert "script-src 'self';" in root.headers["content-security-policy"]


def test_credentials_never_fall_back_to_get_navigation(tmp_path: Path):
    with TestClient(create_app(tmp_path / "entry-forms.db")) as client:
        html = client.get("/").text
        for form in ("bootstrap-form", "login-form", "signup-form", "forced-password-form"):
            tag = re.search(rf'<form[^>]*id="{form}"[^>]*>', html).group()
            assert 'method="post"' in tag


def test_sign_in_explains_the_workspace_and_account_access(tmp_path: Path):
    with TestClient(create_app(tmp_path / "entry-copy.db")) as client:
        javascript = client.get("/static/app.js").text
        assert "Sign in to your workspace" in javascript
        assert "Ask the administrator" in javascript
        assert "Project permissions" in javascript
        assert "window.EntryGate?.ready()" in javascript
        assert "window.EntryGate?.fail(" in javascript
