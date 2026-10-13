"""Verify the dependency-free motion plans, including reduced motion."""
from pathlib import Path
import shutil
import subprocess
import pytest

def test_review_motion_plans():
    node=shutil.which('node')
    if node is None:
        pytest.skip('Node.js is required for browser-model tests')
    result=subprocess.run([node,'--test',str(Path(__file__).with_name('motion_model.test.cjs'))],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
