from pathlib import Path
import shutil
import subprocess
import pytest


def test_commitment_projection_behaviors():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for frontend model verification")
    result = subprocess.run([node, "--test", str(Path(__file__).with_name("commitment_model.test.cjs"))], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
