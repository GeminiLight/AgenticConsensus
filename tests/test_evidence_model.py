"""Exercise the browser's evidence presentation logic without changing admission policy."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_evidence_workbench_behaviors():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is needed for browser model tests")
    result = subprocess.run(
        [node, "--test", str(Path(__file__).with_name("evidence_model.test.cjs"))],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
