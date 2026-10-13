"""Prepare a fresh, English-only StudyShare case without fabricating AI or approval.

The bundled repository is synthetic. Only its existing tests run automatically.
Model suggestions, commitments, verification attestations and decisions must be
created through the application. Existing output directories are never replaced.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from system.services.database import Database
from system.services.review_service import ReviewService


def prepare_case(output: Path) -> dict:
    output = output.expanduser().absolute()
    output.mkdir(parents=True, exist_ok=False)
    repository = output / "studyshare"
    bundle = ROOT / "system/assets/studyshare.bundle"
    subprocess.run(
        ["git", "clone", "--quiet", str(bundle), str(repository)], check=True,
        capture_output=True, text=True, timeout=30,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8"},
    )
    base = "0ca1ebf69c6e35c4dd91110add4b2a071a92d479"
    target = "a71e9a8bc3eb0c6167b3cff8ec937dd5d015a529"
    fixed = "4e965bd23deb04643662ea4f3aef5dacab83cde9"
    database_path = output / "studyshare.db"
    service = ReviewService(Database(database_path))
    project = service.create_project(
        name="StudyShare", repo_path=repository,
        repo_label="studyshare / participant-exports", head_ref=base,
        test_command=["python3", "-m", "unittest", "-q"], claims=[],
    )
    review = service.create_review(
        project.id, base_ref=base, target_ref=target, proposer="Coding agent",
        intent_summary=(
            "Add affiliations to anonymous public exports; keep all private fields out."
        ),
    )
    result = {
        "case": "StudyShare", "language": "en", "synthetic": True,
        "database": str(database_path), "repository": str(repository),
        "project_id": project.id, "review_id": review.id,
        "base_ref": base, "proposal_ref": target, "fixed_ref": fixed,
        "actor": "Research reviewer", "llm_calls_made": 0,
        "approval_recorded": False,
    }
    (output / "case.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New directory; must not already exist")
    args = parser.parse_args()
    print(json.dumps(prepare_case(args.output), indent=2))


if __name__ == "__main__":
    main()
