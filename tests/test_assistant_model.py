from pathlib import Path
import shutil
import subprocess

import pytest


def test_assistant_session_behaviors():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is needed for browser model tests")
    result = subprocess.run(
        [node, "--test", str(Path(__file__).with_name("assistant_model.test.cjs"))],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_suggested_questions_have_group_semantics():
    html = (Path(__file__).resolve().parents[1] / "system/web/static/index.html").read_text()
    assert 'class="copilot-starters" aria-label="Suggested questions" role="group"' in html
