"""Execute the real dependency-free decision inspection planner."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_decision_inspection_planner():
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node.js is required for browser-model tests')
    result = subprocess.run(
        [node, '--test', str(Path(__file__).with_name('decision_model.test.cjs'))],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
