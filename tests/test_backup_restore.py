from __future__ import annotations

import json
import sqlite3
from hashlib import sha256
from pathlib import Path

import pytest

from system.demo import seed_demo
from system.domain.ai import AIAdvisoryRun
from system.main import main
from system.services import database as database_module
from system.services.database import BackupValidationError, Database, database_runtime_lock


class TrackingConnection(sqlite3.Connection):
    was_closed = False

    def close(self) -> None:
        self.was_closed = True
        super().close()


def test_backup_is_a_verified_consistent_snapshot(tmp_path: Path):
    database_path = tmp_path / "control.db"
    seeded = seed_demo(database_path, tmp_path / "demo-repo")
    database = Database(database_path)
    destination = tmp_path / "backups" / "control.db"

    report = database.backup(destination)

    assert destination.is_file()
    manifest_path = destination.with_name(f"{destination.name}.manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert report == manifest
    assert manifest["format"] == "agentic-consensus/database-backup@0.1"
    assert manifest["sha256"] == sha256(destination.read_bytes()).hexdigest()
    assert manifest["health"] == {
        "status": "ok",
        "projects": 1,
        "reviews": 2,
        "events": 2,
            "project_events": 0,
            "intents": 1,
            "ai_runs": 0,
            "ai_feedback": 0,
        }
    assert not Path(f"{destination}-wal").exists()
    assert not Path(f"{destination}-shm").exists()
    assert not list(destination.parent.glob(f".{destination.name}.*.tmp-*"))
    restored_snapshot = Database(destination)
    assert restored_snapshot.get_project(seeded.project_id).id == seeded.project_id
    assert restored_snapshot.get_review(seeded.review_id).id == seeded.review_id


def test_legacy_ai_runs_without_context_versions_remain_readable_but_stale(tmp_path: Path):
    database_path = tmp_path / "legacy-ai.db"
    seeded = seed_demo(database_path, tmp_path / "demo-repo")
    database = Database(database_path)
    review = database.get_review(seeded.review_id)
    run = AIAdvisoryRun(
        id="ai-run-legacy",
        project_id=seeded.project_id,
        review_id=review.id,
        project_version=1,
        review_revision=1,
        feature="review_copilot",
        request="What is blocking this review?",
        result={"answer": "Historical advisory"},
        source="deterministic",
        provider="deterministic",
        prompt_version="legacy-v1",
        context_hash="0" * 64,
        grounded=True,
        citation_precision=1,
        faithfulness_score=1,
        created_by="reviewer",
    )
    legacy_body = run.model_dump(mode="json")
    legacy_body.pop("project_version")
    legacy_body.pop("review_revision")
    with database.connect() as connection:
        connection.execute(
            """INSERT INTO ai_runs(id, project_id, review_id, feature, body, created_at)
               VALUES(?, ?, ?, ?, ?, ?)""",
            (
                run.id,
                run.project_id,
                run.review_id,
                run.feature,
                json.dumps(legacy_body),
                run.created_at.isoformat(),
            ),
        )

    loaded = database.get_ai_run(run.id)

    assert loaded.project_version == 1
    assert loaded.review_revision == 1
    assert "legacy_unversioned_context" in loaded.quality_flags
    assert database.health()["status"] == "ok"
    assert database.backup(tmp_path / "legacy-ai.backup.db")["health"]["ai_runs"] == 1


def test_restore_round_trip_keeps_a_recovery_copy(tmp_path: Path):
    database_path = tmp_path / "control.db"
    seeded = seed_demo(database_path, tmp_path / "demo-repo")
    database = Database(database_path)
    backup_path = tmp_path / "control.backup.db"
    database.backup(backup_path)

    project = database.get_project(seeded.project_id)
    project.name = "mutated after backup"
    database.save_project(project)

    report = database.restore(backup_path)

    assert database.get_project(seeded.project_id).name == "Task-scoped capability migration"
    recovery_path = Path(report["recovery_backup"])
    assert recovery_path.is_file()
    assert Database(recovery_path).get_project(seeded.project_id).name == "mutated after backup"
    assert report["restored_sha256"] == sha256(database_path.read_bytes()).hexdigest()


def test_restore_rejects_a_corrupt_or_manifest_mismatched_backup_without_mutation(tmp_path: Path):
    database_path = tmp_path / "control.db"
    seeded = seed_demo(database_path, tmp_path / "demo-repo")
    database = Database(database_path)
    backup_path = tmp_path / "control.backup.db"
    database.backup(backup_path)
    before = database_path.read_bytes()

    payload = bytearray(backup_path.read_bytes())
    payload[-1] ^= 0x01
    backup_path.write_bytes(payload)

    with pytest.raises(BackupValidationError, match="hash"):
        database.restore(backup_path)

    assert database_path.read_bytes() == before
    assert database.get_project(seeded.project_id).id == seeded.project_id


def test_backup_and_restore_are_operator_commands(tmp_path: Path, capsys):
    database_path = tmp_path / "control.db"
    seeded = seed_demo(database_path, tmp_path / "demo-repo")
    backup_path = tmp_path / "manual.db"

    assert main(["--database", str(database_path), "backup", "--output", str(backup_path)]) == 0
    backup_report = json.loads(capsys.readouterr().out)
    assert backup_report["sha256"] == sha256(backup_path.read_bytes()).hexdigest()

    database = Database(database_path)
    project = database.get_project(seeded.project_id)
    project.name = "temporary mutation"
    database.save_project(project)
    assert main(["--database", str(database_path), "restore", "--input", str(backup_path)]) == 0
    restore_report = json.loads(capsys.readouterr().out)
    assert Path(restore_report["recovery_backup"]).is_file()
    assert Database(database_path).get_project(seeded.project_id).name == "Task-scoped capability migration"


def test_restore_fails_closed_while_the_operator_console_holds_the_database(tmp_path: Path, capsys):
    database_path = tmp_path / "control.db"
    seeded = seed_demo(database_path, tmp_path / "demo-repo")
    database = Database(database_path)
    backup_path = tmp_path / "manual.db"
    database.backup(backup_path)
    before = database_path.read_bytes()

    with database_runtime_lock(database_path):
        result = main(["--database", str(database_path), "restore", "--input", str(backup_path)])

    assert result == 2
    assert "still in use" in capsys.readouterr().err
    assert database_path.read_bytes() == before
    assert database.get_project(seeded.project_id).id == seeded.project_id


def test_restore_recovers_a_corrupt_live_database_and_preserves_the_raw_failure(tmp_path: Path, capsys):
    database_path = tmp_path / "control.db"
    seeded = seed_demo(database_path, tmp_path / "demo-repo")
    backup_path = tmp_path / "known-good.db"
    Database(database_path).backup(backup_path)
    database_path.write_bytes(b"not a sqlite database\n")

    result = main(["--database", str(database_path), "restore", "--input", str(backup_path)])

    assert result == 0
    report = json.loads(capsys.readouterr().out)
    assert report["recovery_backup_validated"] is False
    recovery_path = Path(report["recovery_backup"])
    assert recovery_path.read_bytes() == b"not a sqlite database\n"
    raw_manifest = json.loads(
        recovery_path.with_name(f"{recovery_path.name}.manifest.json").read_text(encoding="utf-8")
    )
    assert raw_manifest["format"] == "agentic-consensus/raw-recovery@0.1"
    assert Database(database_path).get_project(seeded.project_id).id == seeded.project_id


def test_backup_restore_closes_every_owned_sqlite_connection(tmp_path: Path, monkeypatch):
    database_path = tmp_path / "control.db"
    seed_demo(database_path, tmp_path / "demo-repo")
    backup_path = tmp_path / "known-good.db"
    opened: list[TrackingConnection] = []
    real_connect = sqlite3.connect

    def tracked_connect(*args, **kwargs):
        kwargs["factory"] = TrackingConnection
        connection = real_connect(*args, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr(database_module.sqlite3, "connect", tracked_connect)
    database = Database(database_path, initialize=False)

    database.backup(backup_path)
    database.restore(backup_path)

    assert opened
    assert all(connection.was_closed for connection in opened)
