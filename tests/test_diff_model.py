"""Run the same diff model used by the browser, plus its rendering regressions."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_diff_model_behaviors():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is needed for browser model tests")
    result = subprocess.run(
        [node, "--test", str(Path(__file__).with_name("diff_model.test.cjs"))],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_diff_workbench_wires_selection_search_and_direct_finding_navigation():
    root = Path(__file__).resolve().parents[1] / "system/web/static"
    html = (root / "index.html").read_text()
    js = (root / "app.js").read_text()
    assert '/static/diff-model.js' in html
    assert 'DiffModel.fileView' in js
    assert 'id="review-file-select"' in js
    assert 'id="review-file-search"' in js
    assert 'data-open-finding=' in js
    assert 'fileView.selected.file' in js
    assert 'files.map((file) => renderDiffFile(file, review))' not in js
