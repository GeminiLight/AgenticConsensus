"""A preview preserves governed records and excludes account credentials."""
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

from system.services.database import Database


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prepare_review_preview.py"


def prepare(source: Path, output: Path):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--source", str(source), "--output", str(output)],
        capture_output=True, text=True, timeout=30,
    )


def rows(path: Path, table: str):
    with sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True) as connection:
        return connection.execute(f'SELECT * FROM "{table}"').fetchall()


def test_preview_preserves_source_records_without_copying_users(tmp_path):
    source = tmp_path / "source.db"
    original = Database(source)
    body = json.dumps({"repo_path":"/actual/repository", "head_ref":"immutable-commit", "claims":[]})
    with original.connect() as connection:
        connection.execute("INSERT INTO projects VALUES (?,?,?,?)", ("p1", body, "2026-10-08", "2026-10-08"))
        connection.execute(
            "INSERT INTO auth_users (id,username,username_normalized,actor,actor_normalized,role,password_hash,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            ("u1","owner","owner","owner@example.test","owner@example.test","admin","private-test-hash","2026-10-08","2026-10-08"),
        )
    before = {table:rows(source,table) for table in ("projects","auth_users")}
    output = tmp_path / "preview" / "var" / "preview.db"
    result = prepare(source, output)
    assert result.returncode == 0, result.stderr
    assert rows(output, "projects") == before["projects"]
    assert rows(output, "auth_users") == []
    assert rows(output, "auth_sessions") == []
    assert rows(output, "github_connections") == []
    assert {table:rows(source,table) for table in before} == before
    assert json.loads(result.stdout)["credentials_copied"] is False


def test_preview_refuses_to_overwrite_existing_data(tmp_path):
    source = tmp_path / "source.db"
    Database(source)
    output = tmp_path / "existing.db"
    output.write_bytes(b"Existing user data")
    result = prepare(source, output)
    assert result.returncode != 0
    assert "FileExistsError" in result.stderr
    assert output.read_bytes() == b"Existing user data"


def test_missing_source_does_not_create_a_preview(tmp_path):
    output = tmp_path / "preview.db"
    result = prepare(tmp_path / "missing.db", output)
    assert result.returncode != 0
    assert "FileNotFoundError" in result.stderr
    assert not output.exists()
