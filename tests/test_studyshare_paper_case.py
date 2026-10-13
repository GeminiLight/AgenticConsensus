import importlib.util
import json
from pathlib import Path

import pytest

from system.services.database import Database


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prepare_studyshare_case.py"


def load_preparer():
    assert SCRIPT.is_file(), "A repeatable English paper-case preparer is required"
    spec = importlib.util.spec_from_file_location("studyshare_case", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.prepare_case


def test_paper_case_is_english_real_and_not_preapproved(tmp_path):
    result = load_preparer()(tmp_path / "paper-case")
    database = Database(result["database"])
    project = database.get_project(result["project_id"])
    review = database.get_review(result["review_id"])
    assert project.name == "StudyShare"
    assert project.repo_label == "studyshare / participant-exports"
    assert project.version == 1 and not project.commitments
    assert review.status == "open" and not review.decision_records
    assert "affiliation" in review.intent_summary and "private" in review.intent_summary
    assert not any("\u4e00" <= char <= "\u9fff" for char in review.model_dump_json())
    assert not database.list_ai_runs(review_id=review.id)
    tests = next(e for e in review.evidence if e.kind == "tests")
    assert tests.status == "pass" and "Ran 3 tests" in tests.details["output"]
    manifest = json.loads((tmp_path / "paper-case" / "case.json").read_text())
    assert manifest == result
    assert manifest["fixed_ref"].startswith("4e965bd2")


def test_paper_case_refuses_to_overwrite_an_existing_workspace(tmp_path):
    prepare = load_preparer()
    output = tmp_path / "existing"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("Existing user data")
    with pytest.raises(FileExistsError):
        prepare(output)
    assert sentinel.read_text() == "Existing user data"
