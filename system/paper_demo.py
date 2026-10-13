"""Opt-in, password-protected synthetic paper demo. Never a durable workspace."""
from pathlib import Path
import base64
import hashlib
import hmac
import json
import subprocess
import time
import zlib

from system.services.database import Database
from system.services.review_service import ReviewService
from system.services.runtime_tools import git_environment, git_executable


BASE = "0ca1ebf69c6e35c4dd91110add4b2a071a92d479"
PROPOSAL = "a71e9a8bc3eb0c6167b3cff8ec937dd5d015a529"
FIXED = "4e965bd23deb04643662ea4f3aef5dacab83cde9"
TEST_COMMAND = ["python3", "-m", "unittest", "-q"]
NOTICE = ("Research demo · synthetic case · temporary browser session. Export records "
          "before leaving. Model advice is not verification.")
TABLES = ("projects", "reviews", "intents", "audit_events", "project_audit_events", "ai_runs", "ai_feedback")


def read_case_tables(database: Database) -> dict:
    with database.connect() as connection:
        return {table: [dict(row) for row in connection.execute(f'SELECT * FROM "{table}"')]
                for table in TABLES}


def restore_case_tables(database: Database, tables: dict, repository: Path) -> None:
    with database.connect() as connection:
        for table in TABLES:
            columns = [row["name"] for row in connection.execute(f'PRAGMA table_info("{table}")')]
            names = ",".join(f'"{column}"' for column in columns)
            marks = ",".join("?" for _ in columns)
            for row in tables.get(table, []):
                if table == "projects":
                    project = json.loads(row["body"])
                    project["repo_path"] = str(repository)
                    row = {**row, "body": json.dumps(project)}
                connection.execute(f'INSERT INTO "{table}" ({names}) VALUES ({marks})', [row[column] for column in columns])


def seal_case(database: Database, secret: str, owner: str) -> str:
    raw = json.dumps({"version": 1, "owner": owner, "expires": int(time.time()) + 8 * 3600,
                      "tables": read_case_tables(database)}, separators=(",", ":")).encode()
    if len(raw) > 4_000_000:
        raise ValueError("Demo session is full. Export your records and start a new session.")
    encoded = base64.urlsafe_b64encode(zlib.compress(raw)).decode()
    signature = hmac.new(secret.encode(), ("paper-case-v1:" + encoded).encode(), hashlib.sha256).hexdigest()
    return encoded + "." + signature


def open_case(snapshot: str, secret: str, owner: str) -> dict:
    try:
        if len(snapshot) > 900_000:
            raise ValueError("oversized")
        encoded, signature = snapshot.split(".")
        expected = hmac.new(secret.encode(), ("paper-case-v1:" + encoded).encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ValueError("signature")
        unpacker = zlib.decompressobj()
        raw = unpacker.decompress(base64.b64decode(encoded, altchars=b"-_", validate=True), 4_000_001)
        if len(raw) > 4_000_000 or not unpacker.eof:
            raise ValueError("oversized")
        envelope = json.loads(raw)
        if envelope["version"] != 1 or envelope["expires"] < time.time() or not hmac.compare_digest(envelope["owner"], owner):
            raise ValueError("expired or different session")
        return envelope["tables"]
    except (ValueError, KeyError, TypeError, zlib.error) as exc:
        raise ValueError("This temporary demo session is invalid or expired. Export any visible records, then sign out and start again.") from exc


def seed_paper_case(database: Database, repository: Path) -> None:
    projects = database.list_projects()
    if projects:
        if len(projects) != 1 or projects[0].repo_label != "studyshare / participant-exports":
            raise RuntimeError("Paper demo requires its own isolated database")
        return
    if not repository.exists():
        bundle = Path(__file__).parent / "assets" / "studyshare.bundle"
        subprocess.run([git_executable(), "clone", "--quiet", str(bundle), str(repository)],
                       check=True, capture_output=True, timeout=30, env=git_environment())
    service = ReviewService(database)
    project = service.create_project(name="StudyShare", repo_path=repository,
        repo_label="studyshare / participant-exports", head_ref=BASE,
        test_command=TEST_COMMAND, claims=[])
    service.create_review(project.id, base_ref=BASE, target_ref=PROPOSAL,
        proposer="Coding agent", intent_summary=(
            "Add affiliations to anonymous public exports; keep all private fields out."))
