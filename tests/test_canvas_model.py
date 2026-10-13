"""Execute the actual dependency-free browser graph model, not copies of its logic."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_canvas_model_behaviors():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is needed for the browser graph model tests")
    result = subprocess.run(
        [node, "--test", str(Path(__file__).with_name("canvas_model.test.cjs"))],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
