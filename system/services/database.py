from __future__ import annotations

import json
import os
import shutil
import sqlite3
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
from typing import Iterator

import fcntl

from system.domain.ai import AIAdvisoryRun, AIFeedback
from system.domain.models import AuditEvent, IntentMap, Project, ProjectAuditEvent, ReviewPackage


class RecordNotFound(KeyError):
    pass


class ConcurrentTransitionError(RuntimeError):
    """A persisted project or review changed after a transition was prepared."""


class DuplicateReviewRecordError(ValueError):
    """An active review already governs the same base and target revisions."""


class BackupValidationError(RuntimeError):
    """A database backup cannot be trusted for restoration."""


class DatabaseInUseError(RuntimeError):
    """Exclusive database maintenance was attempted during an active runtime session."""


def _lock_path(database_path: str | Path) -> Path:
    path = Path(database_path).expanduser().resolve()
    return path.with_name(f"{path.name}.lock")


@contextmanager
def _database_lock(database_path: str | Path, *, exclusive: bool) -> Iterator[None]:
    lock_path = _lock_path(database_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as lock_file:
        mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        try:
            fcntl.flock(lock_file.fileno(), mode | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise DatabaseInUseError(
                "database is still in use; stop the operator console before offline "
                f"maintenance: {database_path}"
            ) from exc
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def database_runtime_lock(database_path: str | Path) -> Iterator[None]:
    """Hold a shared lock for a process that may read or write the live database."""
    return _database_lock(database_path, exclusive=False)


def database_maintenance_lock(database_path: str | Path) -> Iterator[None]:
    """Hold an exclusive lock while replacing the live database."""
    return _database_lock(database_path, exclusive=True)


class Database:
    def __init__(self, path: str | Path, *, initialize: bool = True):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if initialize:
            self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS reviews (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id),
                    status TEXT NOT NULL,
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS reviews_project_idx ON reviews(project_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS intents (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id),
                    status TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS intents_project_idx ON intents(project_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS audit_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    id TEXT NOT NULL UNIQUE,
                    review_id TEXT NOT NULL REFERENCES reviews(id),
                    action TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS events_review_idx ON audit_events(review_id, sequence);
                CREATE TABLE IF NOT EXISTS project_audit_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    id TEXT NOT NULL UNIQUE,
                    project_id TEXT NOT NULL REFERENCES projects(id),
                    project_version INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS project_events_idx
                    ON project_audit_events(project_id, sequence);
                CREATE TABLE IF NOT EXISTS auth_users (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    username_normalized TEXT NOT NULL UNIQUE,
                    actor TEXT NOT NULL,
                    actor_normalized TEXT NOT NULL UNIQUE,
                    role TEXT NOT NULL CHECK(role IN ('admin', 'operator', 'viewer')),
                    password_hash TEXT NOT NULL,
                    disabled INTEGER NOT NULL DEFAULT 0 CHECK(disabled IN (0, 1)),
                    password_change_required INTEGER NOT NULL DEFAULT 0
                        CHECK(password_change_required IN (0, 1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
                    csrf_token TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS auth_sessions_user_idx
                    ON auth_sessions(user_id, expires_at);
                CREATE TABLE IF NOT EXISTS auth_audit_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    id TEXT NOT NULL UNIQUE,
                    action TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    target_user_id TEXT NOT NULL REFERENCES auth_users(id),
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS github_oauth_states (
                    state_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    redirect_uri TEXT NOT NULL,
                    code_verifier_ciphertext TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS github_oauth_states_expiry_idx
                    ON github_oauth_states(expires_at);
                CREATE TABLE IF NOT EXISTS github_app_manifest_states (
                    state_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
                    origin TEXT NOT NULL,
                    oauth_redirect_uri TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS github_app_manifest_states_expiry_idx
                    ON github_app_manifest_states(expires_at);
                CREATE TABLE IF NOT EXISTS github_app_config (
                    singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1),
                    app_id INTEGER NOT NULL,
                    client_id TEXT NOT NULL,
                    client_secret_ciphertext TEXT NOT NULL,
                    slug TEXT NOT NULL,
                    html_url TEXT NOT NULL,
                    created_by_user_id TEXT NOT NULL REFERENCES auth_users(id),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS github_connections (
                    user_id TEXT PRIMARY KEY REFERENCES auth_users(id) ON DELETE CASCADE,
                    github_user_id INTEGER NOT NULL,
                    login TEXT NOT NULL,
                    access_token_ciphertext TEXT NOT NULL,
                    refresh_token_ciphertext TEXT,
                    token_expires_at TEXT,
                    refresh_token_expires_at TEXT,
                    connected_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ai_runs (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    review_id TEXT REFERENCES reviews(id) ON DELETE SET NULL,
                    feature TEXT NOT NULL,
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ai_runs_project_idx
                    ON ai_runs(project_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS ai_runs_review_idx
                    ON ai_runs(review_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS ai_feedback (
                    run_id TEXT PRIMARY KEY REFERENCES ai_runs(id) ON DELETE CASCADE,
                    verdict TEXT NOT NULL CHECK(verdict IN ('accepted', 'edited', 'rejected')),
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            auth_user_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(auth_users)").fetchall()
            }
            if "password_change_required" not in auth_user_columns:
                connection.execute(
                    """ALTER TABLE auth_users
                       ADD COLUMN password_change_required INTEGER NOT NULL DEFAULT 0
                       CHECK(password_change_required IN (0, 1))"""
                )

    @staticmethod
    def _parse_ai_run(body: str) -> AIAdvisoryRun:
        """Read advisory runs written before context versions became mandatory.

        Versionless runs cannot be proven current. Assign the earliest valid
        snapshot only to keep the historical record readable, and mark it so
        clients do not present it as advice for the active review state.
        """
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise ValueError("AI advisory run body must be a JSON object")
        missing_project_version = "project_version" not in payload
        missing_review_revision = payload.get("review_id") is not None and (
            "review_revision" not in payload or payload["review_revision"] is None
        )
        if missing_project_version:
            payload["project_version"] = 1
        if missing_review_revision:
            payload["review_revision"] = 1
        if missing_project_version or missing_review_revision:
            flags = list(payload.get("quality_flags") or [])
            if "legacy_unversioned_context" not in flags:
                flags.append("legacy_unversioned_context")
            payload["quality_flags"] = flags
        return AIAdvisoryRun.model_validate(payload)

    @staticmethod
    def _manifest_path(database_path: Path) -> Path:
        return database_path.with_name(f"{database_path.name}.manifest.json")

    @staticmethod
    def _sha256(database_path: Path) -> str:
        digest = sha256()
        with database_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _unlink_sqlite_sidecars(database_path: Path) -> None:
        for suffix in ("-wal", "-shm"):
            Path(f"{database_path}{suffix}").unlink(missing_ok=True)

    @classmethod
    def _make_standalone_snapshot(cls, database_path: Path) -> None:
        """Checkpoint a snapshot and make the database file independent of WAL sidecars."""
        with closing(sqlite3.connect(database_path, timeout=10)) as connection:
            with connection:
                connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                mode = connection.execute("PRAGMA journal_mode = DELETE").fetchone()[0]
                if mode.lower() != "delete":
                    raise BackupValidationError(
                        f"could not finalize standalone backup; journal mode is {mode}"
                    )
        cls._unlink_sqlite_sidecars(database_path)

    @staticmethod
    @contextmanager
    def _read_only_connection(database_path: Path) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()

    @classmethod
    def validate_snapshot(cls, database_path: str | Path) -> dict[str, int | str]:
        """Validate SQLite integrity, JSON model shape, and record ownership links."""
        path = Path(database_path).expanduser().resolve()
        if not path.is_file():
            raise BackupValidationError(f"backup database does not exist: {path}")
        try:
            with cls._read_only_connection(path) as connection:
                integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
                if integrity != "ok":
                    raise BackupValidationError(f"SQLite integrity check failed: {integrity}")
                project_rows = connection.execute("SELECT id, body FROM projects").fetchall()
                review_rows = connection.execute("SELECT id, project_id, body FROM reviews").fetchall()
                event_rows = connection.execute("SELECT review_id, body FROM audit_events").fetchall()
                project_event_rows = connection.execute(
                    "SELECT project_id, project_version, body FROM project_audit_events"
                ).fetchall()
                table_names = {
                    row["name"]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }
                intent_rows = (
                    connection.execute(
                        "SELECT id, project_id, revision, body FROM intents"
                    ).fetchall()
                    if "intents" in table_names
                    else []
                )
                auth_user_rows = (
                    connection.execute(
                        "SELECT * FROM auth_users"
                    ).fetchall()
                    if "auth_users" in table_names
                    else []
                )
                auth_session_rows = (
                    connection.execute(
                        "SELECT token_hash, user_id, csrf_token, created_at, expires_at FROM auth_sessions"
                    ).fetchall()
                    if "auth_sessions" in table_names
                    else []
                )
                auth_event_rows = (
                    connection.execute(
                        "SELECT id, action, actor, target_user_id, body, created_at FROM auth_audit_events ORDER BY sequence"
                    ).fetchall()
                    if "auth_audit_events" in table_names
                    else []
                )
                github_state_rows = (
                    connection.execute("SELECT * FROM github_oauth_states").fetchall()
                    if "github_oauth_states" in table_names
                    else []
                )
                github_connection_rows = (
                    connection.execute("SELECT * FROM github_connections").fetchall()
                    if "github_connections" in table_names
                    else []
                )
                github_manifest_state_rows = (
                    connection.execute("SELECT * FROM github_app_manifest_states").fetchall()
                    if "github_app_manifest_states" in table_names
                    else []
                )
                github_app_config_rows = (
                    connection.execute("SELECT * FROM github_app_config").fetchall()
                    if "github_app_config" in table_names
                    else []
                )
                ai_run_rows = (
                    connection.execute(
                        "SELECT id, project_id, review_id, feature, body FROM ai_runs"
                    ).fetchall()
                    if "ai_runs" in table_names
                    else []
                )
                ai_feedback_rows = (
                    connection.execute(
                        "SELECT run_id, verdict, body FROM ai_feedback"
                    ).fetchall()
                    if "ai_feedback" in table_names
                    else []
                )

            projects = {row["id"]: Project.model_validate_json(row["body"]) for row in project_rows}
            reviews = {row["id"]: ReviewPackage.model_validate_json(row["body"]) for row in review_rows}
            intents = {row["id"]: IntentMap.model_validate_json(row["body"]) for row in intent_rows}
            events = [AuditEvent.model_validate_json(row["body"]) for row in event_rows]
            project_events = [
                ProjectAuditEvent.model_validate_json(row["body"]) for row in project_event_rows
            ]
            if any(project.id != project_id for project_id, project in projects.items()):
                raise BackupValidationError("project row id does not match its JSON body")
            for row in review_rows:
                review = reviews[row["id"]]
                if review.id != row["id"] or review.project_id != row["project_id"]:
                    raise BackupValidationError("review row identity does not match its JSON body")
                if review.project_id not in projects:
                    raise BackupValidationError(f"review {review.id} references a missing project")
            for row in intent_rows:
                intent = intents[row["id"]]
                if (
                    intent.id != row["id"]
                    or intent.project_id != row["project_id"]
                    or intent.revision != row["revision"]
                ):
                    raise BackupValidationError("intent row identity does not match its JSON body")
                if intent.project_id not in projects:
                    raise BackupValidationError(f"intent {intent.id} references a missing project")
            for row, event in zip(event_rows, events, strict=True):
                if event.review_id != row["review_id"] or event.review_id not in reviews:
                    raise BackupValidationError("audit event references a missing or mismatched review")
            for row, event in zip(project_event_rows, project_events, strict=True):
                if (
                    event.project_id != row["project_id"]
                    or event.project_id not in projects
                    or event.project_version != row["project_version"]
                ):
                    raise BackupValidationError(
                        "project audit event references a missing or mismatched project version"
                    )
            auth_user_ids = set()
            auth_usernames = set()
            auth_actors = set()
            for row in auth_user_rows:
                if not row["id"] or not row["username"] or not row["actor"]:
                    raise BackupValidationError("authentication user contains an empty identity")
                if row["role"] not in {"admin", "operator", "viewer"}:
                    raise BackupValidationError("authentication user contains an invalid role")
                if row["disabled"] not in {0, 1} or not row["password_hash"]:
                    raise BackupValidationError("authentication user state is invalid")
                if (
                    "password_change_required" in row.keys()
                    and row["password_change_required"] not in {0, 1}
                ):
                    raise BackupValidationError(
                        "authentication password-change state is invalid"
                    )
                if row["username_normalized"] != row["username"].strip().casefold():
                    raise BackupValidationError("authentication username normalization is invalid")
                if row["actor_normalized"] != row["actor"].strip().casefold():
                    raise BackupValidationError("authentication actor normalization is invalid")
                if (
                    row["id"] in auth_user_ids
                    or row["username_normalized"] in auth_usernames
                    or row["actor_normalized"] in auth_actors
                ):
                    raise BackupValidationError("authentication user identity is duplicated")
                datetime.fromisoformat(row["created_at"])
                datetime.fromisoformat(row["updated_at"])
                auth_user_ids.add(row["id"])
                auth_usernames.add(row["username_normalized"])
                auth_actors.add(row["actor_normalized"])
            for row in auth_session_rows:
                if row["user_id"] not in auth_user_ids:
                    raise BackupValidationError("authentication session references a missing user")
                if len(row["token_hash"]) != 64 or not row["csrf_token"]:
                    raise BackupValidationError("authentication session credential shape is invalid")
                datetime.fromisoformat(row["created_at"])
                datetime.fromisoformat(row["expires_at"])
            for row in auth_event_rows:
                if row["target_user_id"] not in auth_user_ids:
                    raise BackupValidationError(
                        "authentication audit event references a missing user"
                    )
                body = json.loads(row["body"])
                if (
                    body.get("id") != row["id"]
                    or body.get("action") != row["action"]
                    or body.get("actor") != row["actor"]
                    or body.get("target_user_id") != row["target_user_id"]
                    or body.get("created_at") != row["created_at"]
                ):
                    raise BackupValidationError(
                        "authentication audit row does not match its JSON body"
                    )
                datetime.fromisoformat(row["created_at"])
            for row in github_state_rows:
                if row["user_id"] not in auth_user_ids:
                    raise BackupValidationError(
                        "GitHub authorization state references a missing local user"
                    )
                if (
                    len(row["state_hash"]) != 64
                    or len(row["code_verifier_ciphertext"]) < 80
                    or not row["redirect_uri"]
                ):
                    raise BackupValidationError("GitHub authorization state shape is invalid")
                datetime.fromisoformat(row["created_at"])
                datetime.fromisoformat(row["expires_at"])
            for row in github_manifest_state_rows:
                if row["user_id"] not in auth_user_ids:
                    raise BackupValidationError(
                        "GitHub App setup state references a missing local user"
                    )
                if (
                    len(row["state_hash"]) != 64
                    or not row["origin"]
                    or not row["oauth_redirect_uri"]
                ):
                    raise BackupValidationError("GitHub App setup state shape is invalid")
                datetime.fromisoformat(row["created_at"])
                datetime.fromisoformat(row["expires_at"])
            if len(github_app_config_rows) > 1:
                raise BackupValidationError("GitHub App configuration is duplicated")
            for row in github_app_config_rows:
                if row["created_by_user_id"] not in auth_user_ids:
                    raise BackupValidationError(
                        "GitHub App configuration references a missing local user"
                    )
                if (
                    row["singleton_id"] != 1
                    or int(row["app_id"]) <= 0
                    or not row["client_id"]
                    or not row["slug"]
                    or not row["html_url"]
                    or len(row["client_secret_ciphertext"]) < 80
                    or row["client_secret_ciphertext"].startswith(("ghs_", "Iv"))
                ):
                    raise BackupValidationError(
                        "GitHub App configuration credential shape is invalid"
                    )
                datetime.fromisoformat(row["created_at"])
                datetime.fromisoformat(row["updated_at"])
            connected_users = set()
            for row in github_connection_rows:
                if row["user_id"] not in auth_user_ids:
                    raise BackupValidationError(
                        "GitHub connection references a missing local user"
                    )
                if row["user_id"] in connected_users:
                    raise BackupValidationError("GitHub connection is duplicated")
                if (
                    int(row["github_user_id"]) <= 0
                    or not row["login"]
                    or len(row["access_token_ciphertext"]) < 80
                    or row["access_token_ciphertext"].startswith(("ghu_", "gho_", "ghp_"))
                ):
                    raise BackupValidationError("GitHub connection credential shape is invalid")
                refresh_ciphertext = row["refresh_token_ciphertext"]
                if refresh_ciphertext and (
                    len(refresh_ciphertext) < 80 or refresh_ciphertext.startswith("ghr_")
                ):
                    raise BackupValidationError("GitHub refresh credential shape is invalid")
                for field in (
                    "token_expires_at",
                    "refresh_token_expires_at",
                    "connected_at",
                    "updated_at",
                ):
                    if row[field]:
                        datetime.fromisoformat(row[field])
                connected_users.add(row["user_id"])
            ai_runs = {row["id"]: cls._parse_ai_run(row["body"]) for row in ai_run_rows}
            for row in ai_run_rows:
                run = ai_runs[row["id"]]
                if (
                    run.id != row["id"]
                    or run.project_id != row["project_id"]
                    or run.review_id != row["review_id"]
                    or run.feature != row["feature"]
                    or run.feedback is not None
                    or run.project_id not in projects
                    or (run.review_id is not None and run.review_id not in reviews)
                    or (
                        run.review_id is not None
                        and reviews[run.review_id].project_id != run.project_id
                    )
                ):
                    raise BackupValidationError(
                        "AI advisory run references a missing or mismatched control object"
                    )
            for row in ai_feedback_rows:
                feedback = AIFeedback.model_validate_json(row["body"])
                if (
                    feedback.run_id != row["run_id"]
                    or feedback.verdict != row["verdict"]
                    or feedback.run_id not in ai_runs
                ):
                    raise BackupValidationError(
                        "AI feedback references a missing or mismatched advisory run"
                    )
        except BackupValidationError:
            raise
        except (sqlite3.Error, ValueError) as exc:
            raise BackupValidationError(f"backup database validation failed: {exc}") from exc
        health = {
            "status": "ok",
            "projects": len(projects),
            "reviews": len(reviews),
            "events": len(events),
            "project_events": len(project_events),
        }
        if "intents" in table_names:
            health["intents"] = len(intents)
        if "ai_runs" in table_names:
            health["ai_runs"] = len(ai_runs)
        if "ai_feedback" in table_names:
            health["ai_feedback"] = len(ai_feedback_rows)
        return health

    def backup(self, destination: str | Path, *, overwrite: bool = False) -> dict:
        """Create an online-consistent SQLite backup and an integrity manifest."""
        target = Path(destination).expanduser().resolve()
        if target == self.path:
            raise ValueError("backup destination must differ from the active database")
        target.parent.mkdir(parents=True, exist_ok=True)
        manifest_path = self._manifest_path(target)
        if not overwrite and (target.exists() or manifest_path.exists()):
            raise FileExistsError(f"backup destination already exists: {target}")

        temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        temporary_manifest = manifest_path.with_name(f".{manifest_path.name}.{uuid4().hex}.tmp")
        try:
            with closing(sqlite3.connect(self.path, timeout=10)) as source, closing(
                sqlite3.connect(temporary)
            ) as sink:
                source.backup(sink)
                sink.commit()
            self._make_standalone_snapshot(temporary)
            os.chmod(temporary, 0o600)
            health = self.validate_snapshot(temporary)
            report = {
                "format": "agentic-consensus/database-backup@0.1",
                "created_at": datetime.now(UTC).isoformat(),
                "sha256": self._sha256(temporary),
                "size_bytes": temporary.stat().st_size,
                "health": health,
            }
            temporary_manifest.write_text(
                json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            os.chmod(temporary_manifest, 0o600)
            self._unlink_sqlite_sidecars(target)
            os.replace(temporary, target)
            os.replace(temporary_manifest, manifest_path)
            return report
        finally:
            temporary.unlink(missing_ok=True)
            self._unlink_sqlite_sidecars(temporary)
            temporary_manifest.unlink(missing_ok=True)

    @classmethod
    def validate_backup(cls, source: str | Path) -> dict:
        backup_path = Path(source).expanduser().resolve()
        manifest_path = cls._manifest_path(backup_path)
        if not manifest_path.is_file():
            raise BackupValidationError(f"backup manifest does not exist: {manifest_path}")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BackupValidationError(f"backup manifest is invalid: {exc}") from exc
        if manifest.get("format") != "agentic-consensus/database-backup@0.1":
            raise BackupValidationError("backup manifest format is unsupported")
        expected_hash = manifest.get("sha256")
        actual_hash = cls._sha256(backup_path) if backup_path.is_file() else "missing"
        if expected_hash != actual_hash:
            raise BackupValidationError(
                f"backup hash mismatch: expected {expected_hash}; observed {actual_hash}"
            )
        health = cls.validate_snapshot(backup_path)
        if manifest.get("health") != health:
            raise BackupValidationError("backup record counts do not match the manifest")
        return manifest

    def _preserve_raw_recovery(self, recovery_path: Path, validation_error: Exception) -> None:
        """Retain an invalid live database byte-for-byte for later diagnosis."""
        shutil.copy2(self.path, recovery_path)
        os.chmod(recovery_path, 0o600)
        sidecars = []
        for suffix in ("-wal", "-shm"):
            source_sidecar = Path(f"{self.path}{suffix}")
            if not source_sidecar.is_file():
                continue
            recovery_sidecar = Path(f"{recovery_path}{suffix}")
            shutil.copy2(source_sidecar, recovery_sidecar)
            os.chmod(recovery_sidecar, 0o600)
            sidecars.append(
                {
                    "suffix": suffix,
                    "sha256": self._sha256(recovery_sidecar),
                    "size_bytes": recovery_sidecar.stat().st_size,
                }
            )
        manifest = {
            "format": "agentic-consensus/raw-recovery@0.1",
            "created_at": datetime.now(UTC).isoformat(),
            "sha256": self._sha256(recovery_path),
            "size_bytes": recovery_path.stat().st_size,
            "validated": False,
            "validation_error": str(validation_error)[:1000],
            "sidecars": sidecars,
        }
        manifest_path = self._manifest_path(recovery_path)
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        os.chmod(manifest_path, 0o600)

    def restore(self, source: str | Path) -> dict:
        """Restore a verified snapshot after retaining a verified recovery copy."""
        backup_path = Path(source).expanduser().resolve()
        if backup_path == self.path:
            raise ValueError("restore source must differ from the active database")
        with database_maintenance_lock(self.path):
            source_manifest = self.validate_backup(backup_path)
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
            recovery_path = self.path.with_name(
                f"{self.path.stem}.pre-restore-{timestamp}{self.path.suffix}"
            )
            recovery_backup_validated: bool | None = None
            if self.path.is_file():
                try:
                    self.backup(recovery_path)
                    recovery_backup_validated = True
                except (BackupValidationError, sqlite3.Error) as exc:
                    self._preserve_raw_recovery(recovery_path, exc)
                    recovery_backup_validated = False

            temporary = self.path.with_name(f".{self.path.name}.{uuid4().hex}.restore")
            try:
                with self._read_only_connection(backup_path) as source_connection, closing(
                    sqlite3.connect(temporary)
                ) as target_connection:
                    source_connection.backup(target_connection)
                    target_connection.commit()
                self._make_standalone_snapshot(temporary)
                os.chmod(temporary, 0o600)
                self.validate_snapshot(temporary)
                if recovery_backup_validated:
                    with closing(sqlite3.connect(self.path, timeout=10)) as current:
                        with current:
                            current.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                self._unlink_sqlite_sidecars(self.path)
                os.replace(temporary, self.path)
                self.initialize()
                restored_health = self.validate_snapshot(self.path)
            except Exception:
                temporary.unlink(missing_ok=True)
                self._unlink_sqlite_sidecars(temporary)
                raise
        return {
            "format": "agentic-consensus/database-restore@0.1",
            "restored_at": datetime.now(UTC).isoformat(),
            "source_sha256": source_manifest["sha256"],
            "restored_sha256": self._sha256(self.path),
            "recovery_backup": str(recovery_path) if recovery_backup_validated is not None else None,
            "recovery_backup_validated": recovery_backup_validated,
            "health": restored_health,
        }

    @staticmethod
    def _json(
        model: Project
        | IntentMap
        | ReviewPackage
        | AuditEvent
        | ProjectAuditEvent
        | AIAdvisoryRun
        | AIFeedback,
    ) -> str:
        return json.dumps(model.model_dump(mode="json"), separators=(",", ":"), ensure_ascii=False)

    def save_project(self, project: Project) -> None:
        body = self._json(project)
        created_at = project.created_at.isoformat()
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO projects(id, body, created_at) VALUES(?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET body=excluded.body, updated_at=CURRENT_TIMESTAMP""",
                (project.id, body, created_at),
            )

    def find_project_by_github_repository(self, repository_id: int) -> Project | None:
        for project in self.list_projects():
            if (
                project.source is not None
                and project.source.provider == "github"
                and project.source.repository_id == repository_id
            ):
                return project
        return None

    def save_github_oauth_state(self, record: dict) -> None:
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM github_oauth_states WHERE expires_at <= ?",
                (datetime.now(UTC).isoformat(),),
            )
            connection.execute(
                """INSERT INTO github_oauth_states(
                       state_hash, user_id, redirect_uri, code_verifier_ciphertext,
                       created_at, expires_at
                   ) VALUES(?, ?, ?, ?, ?, ?)""",
                (
                    record["state_hash"],
                    record["user_id"],
                    record["redirect_uri"],
                    record["code_verifier_ciphertext"],
                    record["created_at"],
                    record["expires_at"],
                ),
            )

    def consume_github_oauth_state(self, state_hash: str) -> dict | None:
        """Atomically return and delete a live OAuth state so it cannot be replayed."""
        now = datetime.now(UTC).isoformat()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM github_oauth_states WHERE state_hash = ?",
                (state_hash,),
            ).fetchone()
            connection.execute(
                "DELETE FROM github_oauth_states WHERE state_hash = ? OR expires_at <= ?",
                (state_hash, now),
            )
            if row is None or row["expires_at"] <= now:
                return None
            return dict(row)

    def save_github_app_manifest_state(self, record: dict) -> None:
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM github_app_manifest_states WHERE expires_at <= ?",
                (datetime.now(UTC).isoformat(),),
            )
            connection.execute(
                """INSERT INTO github_app_manifest_states(
                       state_hash, user_id, origin, oauth_redirect_uri,
                       created_at, expires_at
                   ) VALUES(?, ?, ?, ?, ?, ?)""",
                (
                    record["state_hash"],
                    record["user_id"],
                    record["origin"],
                    record["oauth_redirect_uri"],
                    record["created_at"],
                    record["expires_at"],
                ),
            )

    def consume_github_app_manifest_state(self, state_hash: str) -> dict | None:
        """Atomically return and delete a live App Manifest state."""
        now = datetime.now(UTC).isoformat()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM github_app_manifest_states WHERE state_hash = ?",
                (state_hash,),
            ).fetchone()
            connection.execute(
                "DELETE FROM github_app_manifest_states WHERE state_hash = ? OR expires_at <= ?",
                (state_hash, now),
            )
            if row is None or row["expires_at"] <= now:
                return None
            return dict(row)

    def save_github_app_config(self, record: dict) -> bool:
        """Persist the singleton GitHub App returned by the one-time manifest flow."""
        with self.connect() as connection:
            cursor = connection.execute(
                """INSERT OR IGNORE INTO github_app_config(
                       singleton_id, app_id, client_id, client_secret_ciphertext,
                       slug, html_url, created_by_user_id, created_at, updated_at
                   ) VALUES(1, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record["app_id"],
                    record["client_id"],
                    record["client_secret_ciphertext"],
                    record["slug"],
                    record["html_url"],
                    record["created_by_user_id"],
                    record["created_at"],
                    record["updated_at"],
                ),
            )
            return cursor.rowcount > 0

    def get_github_app_config(self) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM github_app_config WHERE singleton_id = 1"
            ).fetchone()
            return dict(row) if row is not None else None

    def save_github_connection(self, record: dict) -> None:
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO github_connections(
                       user_id, github_user_id, login, access_token_ciphertext,
                       refresh_token_ciphertext, token_expires_at,
                       refresh_token_expires_at, connected_at, updated_at
                   ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET
                       github_user_id=excluded.github_user_id,
                       login=excluded.login,
                       access_token_ciphertext=excluded.access_token_ciphertext,
                       refresh_token_ciphertext=excluded.refresh_token_ciphertext,
                       token_expires_at=excluded.token_expires_at,
                       refresh_token_expires_at=excluded.refresh_token_expires_at,
                       connected_at=excluded.connected_at,
                       updated_at=excluded.updated_at""",
                (
                    record["user_id"],
                    record["github_user_id"],
                    record["login"],
                    record["access_token_ciphertext"],
                    record.get("refresh_token_ciphertext"),
                    record.get("token_expires_at"),
                    record.get("refresh_token_expires_at"),
                    record["connected_at"],
                    record["updated_at"],
                ),
            )

    def get_github_connection(self, user_id: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM github_connections WHERE user_id = ?", (user_id,)
            ).fetchone()
            return dict(row) if row is not None else None

    def delete_github_connection(self, user_id: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM github_connections WHERE user_id = ?", (user_id,)
            )
            return cursor.rowcount > 0

    def auth_user_count(self) -> int:
        with self.connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM auth_users").fetchone()[0])

    def create_first_auth_user(self, record: dict, event: dict) -> None:
        """Atomically create the sole bootstrap administrator."""
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute("SELECT 1 FROM auth_users LIMIT 1").fetchone() is not None:
                raise ValueError("authentication is already initialized")
            self._insert_auth_user(connection, record)
            self._insert_auth_event(connection, event)

    def create_auth_user(self, record: dict, event: dict) -> None:
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._insert_auth_user(connection, record)
            self._insert_auth_event(connection, event)

    @staticmethod
    def _insert_auth_user(connection: sqlite3.Connection, record: dict) -> None:
        connection.execute(
            """INSERT INTO auth_users(
                id, username, username_normalized, actor, actor_normalized, role,
                password_hash, disabled, password_change_required, created_at, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record["id"],
                record["username"],
                record["username_normalized"],
                record["actor"],
                record["actor_normalized"],
                record["role"],
                record["password_hash"],
                int(record.get("disabled", False)),
                int(record.get("password_change_required", False)),
                record["created_at"],
                record["updated_at"],
            ),
        )

    @staticmethod
    def _insert_auth_event(connection: sqlite3.Connection, event: dict) -> None:
        body = json.dumps(event, separators=(",", ":"), ensure_ascii=False)
        connection.execute(
            """INSERT INTO auth_audit_events(
                id, action, actor, target_user_id, body, created_at
            ) VALUES(?, ?, ?, ?, ?, ?)""",
            (
                event["id"],
                event["action"],
                event["actor"],
                event["target_user_id"],
                body,
                event["created_at"],
            ),
        )

    def get_auth_user_by_username(self, username_normalized: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM auth_users WHERE username_normalized = ?",
                (username_normalized,),
            ).fetchone()
        return dict(row) if row is not None else None

    def get_auth_user(self, user_id: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM auth_users WHERE id = ?", (user_id,)
            ).fetchone()
        return dict(row) if row is not None else None

    def list_auth_users(self) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM auth_users ORDER BY created_at, username_normalized"
            ).fetchall()
        return [dict(row) for row in rows]

    def update_auth_password_hash(self, user_id: str, password_hash: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE auth_users SET password_hash = ?, updated_at = ? WHERE id = ?",
                (password_hash, datetime.now(UTC).isoformat(), user_id),
            )

    def replace_auth_password(
        self,
        *,
        user_id: str,
        expected_password_hash: str,
        password_hash: str,
        password_change_required: bool,
        event: dict,
    ) -> tuple[dict, int]:
        """Replace one password, revoke its sessions, and append the audit event atomically."""
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM auth_users WHERE id = ?", (user_id,)
            ).fetchone()
            if row is None:
                raise KeyError(user_id)
            if row["disabled"]:
                raise ValueError("disabled identity cannot change its password")
            if row["password_hash"] != expected_password_hash:
                raise ValueError("password changed concurrently")
            now = datetime.now(UTC).isoformat()
            connection.execute(
                """UPDATE auth_users
                   SET password_hash = ?, password_change_required = ?, updated_at = ?
                   WHERE id = ?""",
                (password_hash, int(password_change_required), now, user_id),
            )
            revoked_sessions = int(
                connection.execute(
                    "SELECT COUNT(*) FROM auth_sessions WHERE user_id = ?", (user_id,)
                ).fetchone()[0]
            )
            connection.execute("DELETE FROM auth_sessions WHERE user_id = ?", (user_id,))
            event["payload"]["revoked_sessions"] = str(revoked_sessions)
            self._insert_auth_event(connection, event)
            updated = connection.execute(
                "SELECT * FROM auth_users WHERE id = ?", (user_id,)
            ).fetchone()
        return dict(updated), revoked_sessions

    def revoke_other_auth_sessions(
        self, *, user_id: str, current_token_hash: str, event: dict
    ) -> int:
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            exists = connection.execute(
                "SELECT 1 FROM auth_users WHERE id = ? AND disabled = 0", (user_id,)
            ).fetchone()
            if exists is None:
                raise KeyError(user_id)
            revoked = int(
                connection.execute(
                    """SELECT COUNT(*) FROM auth_sessions
                       WHERE user_id = ? AND token_hash != ?""",
                    (user_id, current_token_hash),
                ).fetchone()[0]
            )
            connection.execute(
                "DELETE FROM auth_sessions WHERE user_id = ? AND token_hash != ?",
                (user_id, current_token_hash),
            )
            event["payload"]["revoked_sessions"] = str(revoked)
            self._insert_auth_event(connection, event)
        return revoked

    def set_auth_user_disabled(
        self, user_id: str, disabled: bool, event: dict
    ) -> dict | None:
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM auth_users WHERE id = ?", (user_id,)
            ).fetchone()
            if row is None:
                return None
            if disabled and row["role"] == "admin" and not row["disabled"]:
                active_admins = connection.execute(
                    "SELECT COUNT(*) FROM auth_users WHERE role = 'admin' AND disabled = 0"
                ).fetchone()[0]
                if active_admins <= 1:
                    raise ValueError("the last active administrator cannot be disabled")
            now = datetime.now(UTC).isoformat()
            connection.execute(
                "UPDATE auth_users SET disabled = ?, updated_at = ? WHERE id = ?",
                (int(disabled), now, user_id),
            )
            if disabled:
                connection.execute("DELETE FROM auth_sessions WHERE user_id = ?", (user_id,))
            self._insert_auth_event(connection, event)
            updated = connection.execute(
                "SELECT * FROM auth_users WHERE id = ?", (user_id,)
            ).fetchone()
        return dict(updated)

    def create_auth_session(self, record: dict) -> None:
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM auth_sessions WHERE expires_at <= ?",
                (datetime.now(UTC).isoformat(),),
            )
            connection.execute(
                """INSERT INTO auth_sessions(
                    token_hash, user_id, csrf_token, created_at, expires_at
                ) VALUES(?, ?, ?, ?, ?)""",
                (
                    record["token_hash"],
                    record["user_id"],
                    record["csrf_token"],
                    record["created_at"],
                    record["expires_at"],
                ),
            )

    def get_auth_session(self, token_hash: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                """SELECT s.token_hash, s.user_id, s.csrf_token, s.created_at AS session_created_at,
                          s.expires_at, u.id, u.username, u.username_normalized, u.actor,
                          u.actor_normalized, u.role, u.password_hash, u.disabled,
                          u.password_change_required, u.created_at, u.updated_at
                   FROM auth_sessions AS s
                   JOIN auth_users AS u ON u.id = s.user_id
                   WHERE s.token_hash = ?""",
                (token_hash,),
            ).fetchone()
        return dict(row) if row is not None else None

    def delete_auth_session(self, token_hash: str) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (token_hash,))

    def list_auth_events(self) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT body FROM auth_audit_events ORDER BY sequence"
            ).fetchall()
        return [json.loads(row["body"]) for row in rows]

    def get_project(self, project_id: str) -> Project:
        with self.connect() as connection:
            row = connection.execute("SELECT body FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            raise RecordNotFound(project_id)
        return Project.model_validate_json(row["body"])

    def list_projects(self) -> list[Project]:
        with self.connect() as connection:
            rows = connection.execute("SELECT body FROM projects ORDER BY created_at DESC").fetchall()
        return [Project.model_validate_json(row["body"]) for row in rows]

    def find_project_by_repo(self, repo_path: str | Path) -> Project | None:
        resolved = str(Path(repo_path).expanduser().resolve())
        return next((project for project in self.list_projects() if project.repo_path == resolved), None)

    def delete_project_data(self, project_id: str) -> None:
        """Delete one explicitly identified project and its dependent local records."""
        with self.connect() as connection:
            review_rows = connection.execute("SELECT id FROM reviews WHERE project_id = ?", (project_id,)).fetchall()
            review_ids = [row["id"] for row in review_rows]
            if review_ids:
                placeholders = ",".join("?" for _ in review_ids)
                connection.execute(f"DELETE FROM audit_events WHERE review_id IN ({placeholders})", review_ids)
            connection.execute("DELETE FROM reviews WHERE project_id = ?", (project_id,))
            connection.execute("DELETE FROM intents WHERE project_id = ?", (project_id,))
            connection.execute("DELETE FROM project_audit_events WHERE project_id = ?", (project_id,))
            connection.execute("DELETE FROM projects WHERE id = ?", (project_id,))

    def save_ai_run(self, run: AIAdvisoryRun) -> None:
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            project_row = connection.execute(
                "SELECT body FROM projects WHERE id = ?", (run.project_id,)
            ).fetchone()
            if project_row is None:
                raise RecordNotFound(run.project_id)
            project = Project.model_validate_json(project_row["body"])
            if project.version != run.project_version:
                raise ConcurrentTransitionError(
                    "project state changed while the AI advisory run was being saved"
                )
            if run.review_id is not None:
                review_row = connection.execute(
                    "SELECT project_id, body FROM reviews WHERE id = ?", (run.review_id,)
                ).fetchone()
                if review_row is None:
                    raise RecordNotFound(run.review_id)
                if review_row["project_id"] != run.project_id:
                    raise ValueError(
                        "AI advisory run and review must belong to the same project"
                    )
                review = ReviewPackage.model_validate_json(review_row["body"])
                if run.review_revision != review.revision:
                    raise ConcurrentTransitionError(
                        "review evidence changed while the AI advisory run was being saved"
                    )
            connection.execute(
                """INSERT INTO ai_runs(id, project_id, review_id, feature, body, created_at)
                VALUES(?, ?, ?, ?, ?, ?)""",
                (
                    run.id,
                    run.project_id,
                    run.review_id,
                    run.feature,
                    self._json(run.model_copy(update={"feedback": None})),
                    run.created_at.isoformat(),
                ),
            )

    def save_ai_feedback(self, feedback: AIFeedback) -> None:
        with self.connect() as connection:
            if connection.execute(
                "SELECT 1 FROM ai_runs WHERE id = ?", (feedback.run_id,)
            ).fetchone() is None:
                raise RecordNotFound(feedback.run_id)
            connection.execute(
                """INSERT INTO ai_feedback(run_id, verdict, body, created_at)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET verdict=excluded.verdict,
                    body=excluded.body, created_at=excluded.created_at""",
                (
                    feedback.run_id,
                    feedback.verdict,
                    self._json(feedback),
                    feedback.created_at.isoformat(),
                ),
            )

    def _ai_run_from_row(self, row: sqlite3.Row) -> AIAdvisoryRun:
        run = self._parse_ai_run(row["body"])
        feedback_body = row["feedback_body"] if "feedback_body" in row.keys() else None
        if feedback_body:
            run = run.model_copy(update={"feedback": AIFeedback.model_validate_json(feedback_body)})
        return run

    def get_ai_run(self, run_id: str) -> AIAdvisoryRun:
        with self.connect() as connection:
            row = connection.execute(
                """SELECT runs.body, feedback.body AS feedback_body
                FROM ai_runs AS runs
                LEFT JOIN ai_feedback AS feedback ON feedback.run_id = runs.id
                WHERE runs.id = ?""",
                (run_id,),
            ).fetchone()
        if row is None:
            raise RecordNotFound(run_id)
        return self._ai_run_from_row(row)

    def list_ai_runs(
        self,
        *,
        project_id: str | None = None,
        review_id: str | None = None,
        limit: int = 100,
    ) -> list[AIAdvisoryRun]:
        clauses: list[str] = []
        values: list[str | int] = []
        if project_id is not None:
            clauses.append("runs.project_id = ?")
            values.append(project_id)
        if review_id is not None:
            clauses.append("runs.review_id = ?")
            values.append(review_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        values.append(min(max(limit, 1), 500))
        with self.connect() as connection:
            rows = connection.execute(
                f"""SELECT runs.body, feedback.body AS feedback_body
                FROM ai_runs AS runs
                LEFT JOIN ai_feedback AS feedback ON feedback.run_id = runs.id
                {where}
                ORDER BY runs.created_at DESC LIMIT ?""",
                values,
            ).fetchall()
        return [self._ai_run_from_row(row) for row in rows]

    def save_intent(self, intent: IntentMap) -> None:
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO intents(id, project_id, status, revision, body, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET status=excluded.status,
                    revision=excluded.revision, body=excluded.body, updated_at=excluded.updated_at""",
                (
                    intent.id,
                    intent.project_id,
                    intent.status,
                    intent.revision,
                    self._json(intent),
                    intent.created_at.isoformat(),
                    intent.updated_at.isoformat(),
                ),
            )

    def get_intent(self, intent_id: str) -> IntentMap:
        with self.connect() as connection:
            row = connection.execute("SELECT body FROM intents WHERE id = ?", (intent_id,)).fetchone()
        if row is None:
            raise RecordNotFound(intent_id)
        return IntentMap.model_validate_json(row["body"])

    def list_intents(self, project_id: str | None = None) -> list[IntentMap]:
        query = "SELECT body FROM intents"
        params: tuple[str, ...] = ()
        if project_id:
            query += " WHERE project_id = ?"
            params = (project_id,)
        query += " ORDER BY created_at DESC"
        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [IntentMap.model_validate_json(row["body"]) for row in rows]

    def apply_intent_transition(self, intent: IntentMap, *, expected_revision: int) -> None:
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT body FROM intents WHERE id = ?", (intent.id,)).fetchone()
            if row is None:
                raise RecordNotFound(intent.id)
            current = IntentMap.model_validate_json(row["body"])
            if current.revision != expected_revision:
                raise ConcurrentTransitionError(
                    f"stale intent state: expected revision {expected_revision}; "
                    f"current revision is {current.revision}"
                )
            if intent.revision != expected_revision + 1:
                raise ValueError("intent transition must advance exactly one revision")
            connection.execute(
                """UPDATE intents SET status = ?, revision = ?, body = ?, updated_at = ?
                   WHERE id = ?""",
                (
                    intent.status,
                    intent.revision,
                    self._json(intent),
                    intent.updated_at.isoformat(),
                    intent.id,
                ),
            )

    def apply_realization_transition(
        self,
        *,
        intent: IntentMap,
        review: ReviewPackage,
        event: AuditEvent,
        expected_intent_revision: int,
    ) -> None:
        """Atomically link one successful realization, review, and creation event."""
        if (
            intent.project_id != review.project_id
            or review.intent_id != intent.id
            or intent.realized_review_id != review.id
            or event.review_id != review.id
        ):
            raise ValueError("realization records do not form one linked transition")
        if intent.revision != expected_intent_revision + 1:
            raise ValueError("intent transition must advance exactly one revision")

        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT body FROM intents WHERE id = ?", (intent.id,)
            ).fetchone()
            if row is None:
                raise RecordNotFound(intent.id)
            current = IntentMap.model_validate_json(row["body"])
            if current.revision != expected_intent_revision:
                raise ConcurrentTransitionError(
                    f"stale intent state: expected revision {expected_intent_revision}; "
                    f"current revision is {current.revision}"
                )
            self._require_unique_active_review(connection, review)
            connection.execute(
                """INSERT INTO reviews(id, project_id, status, body, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?)""",
                (
                    review.id,
                    review.project_id,
                    review.status,
                    self._json(review),
                    review.created_at.isoformat(),
                    review.updated_at.isoformat(),
                ),
            )
            connection.execute(
                """INSERT INTO audit_events(id, review_id, action, actor, body, created_at)
                VALUES(?, ?, ?, ?, ?, ?)""",
                (
                    event.id,
                    event.review_id,
                    event.action,
                    event.actor,
                    self._json(event),
                    event.created_at.isoformat(),
                ),
            )
            connection.execute(
                """UPDATE intents SET status = ?, revision = ?, body = ?, updated_at = ?
                   WHERE id = ?""",
                (
                    intent.status,
                    intent.revision,
                    self._json(intent),
                    intent.updated_at.isoformat(),
                    intent.id,
                ),
            )

    def apply_project_transition(
        self,
        *,
        project: Project,
        event: ProjectAuditEvent,
        expected_project_version: int,
    ) -> None:
        """Persist one project-level governance transition and its audit event atomically."""
        if event.project_id != project.id or event.project_version != project.version:
            raise ValueError("project transition event does not match the resulting project state")

        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT body FROM projects WHERE id = ?", (project.id,)
            ).fetchone()
            if row is None:
                raise RecordNotFound(project.id)
            current = Project.model_validate_json(row["body"])
            if current.version != expected_project_version:
                raise ConcurrentTransitionError(
                    "concurrent project-state update: "
                    f"expected C^{expected_project_version}; current state is C^{current.version}"
                )
            connection.execute(
                "UPDATE projects SET body = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (self._json(project), project.id),
            )
            connection.execute(
                """INSERT INTO project_audit_events(
                    id, project_id, project_version, action, actor, body, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.id,
                    event.project_id,
                    event.project_version,
                    event.action,
                    event.actor,
                    self._json(event),
                    event.created_at.isoformat(),
                ),
            )

    def save_review(self, review: ReviewPackage) -> None:
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO reviews(id, project_id, status, body, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status, body=excluded.body, updated_at=excluded.updated_at""",
                (
                    review.id,
                    review.project_id,
                    review.status,
                    self._json(review),
                    review.created_at.isoformat(),
                    review.updated_at.isoformat(),
                ),
            )

    @staticmethod
    def _require_unique_active_review(
        connection: sqlite3.Connection, review: ReviewPackage
    ) -> None:
        rows = connection.execute(
            "SELECT body FROM reviews WHERE project_id = ?", (review.project_id,)
        ).fetchall()
        for row in rows:
            current = ReviewPackage.model_validate_json(row["body"])
            if (
                current.base_ref == review.base_ref
                and current.target_ref == review.target_ref
                and current.status in {"open", "committed"}
            ):
                raise DuplicateReviewRecordError(
                    f"review for these revisions already exists: {current.id}"
                )

    def create_review(self, review: ReviewPackage, event: AuditEvent) -> None:
        """Insert a review and its creation event in one transaction."""
        if event.review_id != review.id or event.action != "create_review":
            raise ValueError("review creation event does not match the review")
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if review.predecessor_review_id:
                row = connection.execute("SELECT body FROM reviews WHERE id = ?", (review.predecessor_review_id,)).fetchone()
                parent = ReviewPackage.model_validate_json(row["body"]) if row else None
                project_row = connection.execute("SELECT body FROM projects WHERE id = ?", (review.project_id,)).fetchone()
                project = Project.model_validate_json(project_row["body"]) if project_row else None
                if not parent or parent.project_id != review.project_id or parent.status != "rebase_required" or parent.revision != review.predecessor_revision:
                    raise ConcurrentTransitionError("the previous review changed; reload before reviewing a revision")
                if not project or project.version != review.base_version:
                    raise ConcurrentTransitionError("the project baseline changed; reload before reviewing a revision")
            self._require_unique_active_review(connection, review)
            connection.execute(
                """INSERT INTO reviews(id, project_id, status, body, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?)""",
                (
                    review.id,
                    review.project_id,
                    review.status,
                    self._json(review),
                    review.created_at.isoformat(),
                    review.updated_at.isoformat(),
                ),
            )
            connection.execute(
                """INSERT INTO audit_events(id, review_id, action, actor, body, created_at)
                VALUES(?, ?, ?, ?, ?, ?)""",
                (
                    event.id,
                    event.review_id,
                    event.action,
                    event.actor,
                    self._json(event),
                    event.created_at.isoformat(),
                ),
            )

    def get_review(self, review_id: str) -> ReviewPackage:
        with self.connect() as connection:
            row = connection.execute("SELECT body FROM reviews WHERE id = ?", (review_id,)).fetchone()
        if row is None:
            raise RecordNotFound(review_id)
        return ReviewPackage.model_validate_json(row["body"])

    def list_reviews(self, project_id: str | None = None) -> list[ReviewPackage]:
        query = "SELECT body FROM reviews"
        params: tuple[str, ...] = ()
        if project_id:
            query += " WHERE project_id = ?"
            params = (project_id,)
        query += " ORDER BY created_at DESC"
        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [ReviewPackage.model_validate_json(row["body"]) for row in rows]

    def append_event(self, event: AuditEvent) -> None:
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO audit_events(id, review_id, action, actor, body, created_at)
                VALUES(?, ?, ?, ?, ?, ?)""",
                (event.id, event.review_id, event.action, event.actor, self._json(event), event.created_at.isoformat()),
            )

    def apply_review_transition(
        self,
        *,
        review: ReviewPackage,
        event: AuditEvent,
        expected_review_revision: int,
    ) -> None:
        """Persist one review-only transition and its event with a revision CAS."""
        if event.review_id != review.id:
            raise ValueError("review transition event does not match the review")
        if review.revision != expected_review_revision + 1:
            raise ValueError("review transition must advance exactly one revision")

        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT body FROM reviews WHERE id = ?", (review.id,)
            ).fetchone()
            if row is None:
                raise RecordNotFound(review.id)
            current = ReviewPackage.model_validate_json(row["body"])
            if current.revision != expected_review_revision:
                raise ConcurrentTransitionError(
                    "concurrent review update: "
                    f"expected revision {expected_review_revision}; "
                    f"current revision is {current.revision}"
                )
            connection.execute(
                """UPDATE reviews SET status = ?, body = ?, updated_at = ? WHERE id = ?""",
                (
                    review.status,
                    self._json(review),
                    review.updated_at.isoformat(),
                    review.id,
                ),
            )
            connection.execute(
                """INSERT INTO audit_events(id, review_id, action, actor, body, created_at)
                VALUES(?, ?, ?, ?, ?, ?)""",
                (
                    event.id,
                    event.review_id,
                    event.action,
                    event.actor,
                    self._json(event),
                    event.created_at.isoformat(),
                ),
            )

    def apply_transition(
        self,
        *,
        project: Project,
        review: ReviewPackage,
        event: AuditEvent,
        expected_project_version: int,
        expected_review_revision: int,
    ) -> None:
        """Persist one governed transition atomically with optimistic concurrency checks."""
        if review.project_id != project.id or event.review_id != review.id:
            raise ValueError("transition records do not belong to the same project review")

        with self.connect() as connection:
            # Acquire the SQLite write reservation before reading versions. A competing
            # writer must finish before these checks, so stale decisions fail closed.
            connection.execute("BEGIN IMMEDIATE")
            project_row = connection.execute(
                "SELECT body FROM projects WHERE id = ?", (project.id,)
            ).fetchone()
            review_row = connection.execute(
                "SELECT body FROM reviews WHERE id = ?", (review.id,)
            ).fetchone()
            if project_row is None:
                raise RecordNotFound(project.id)
            if review_row is None:
                raise RecordNotFound(review.id)

            current_project = Project.model_validate_json(project_row["body"])
            current_review = ReviewPackage.model_validate_json(review_row["body"])
            if current_project.version != expected_project_version:
                raise ConcurrentTransitionError(
                    "concurrent project-state update: "
                    f"expected C^{expected_project_version}; current state is C^{current_project.version}"
                )
            if current_review.revision != expected_review_revision:
                raise ConcurrentTransitionError(
                    "concurrent review update: "
                    f"expected revision {expected_review_revision}; current revision is {current_review.revision}"
                )

            connection.execute(
                "UPDATE projects SET body = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (self._json(project), project.id),
            )
            connection.execute(
                """UPDATE reviews SET status = ?, body = ?, updated_at = ? WHERE id = ?""",
                (review.status, self._json(review), review.updated_at.isoformat(), review.id),
            )
            connection.execute(
                """INSERT INTO audit_events(id, review_id, action, actor, body, created_at)
                VALUES(?, ?, ?, ?, ?, ?)""",
                (
                    event.id,
                    event.review_id,
                    event.action,
                    event.actor,
                    self._json(event),
                    event.created_at.isoformat(),
                ),
            )

    def list_events(self, review_id: str) -> list[AuditEvent]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT body FROM audit_events WHERE review_id = ? ORDER BY sequence", (review_id,)
            ).fetchall()
        return [AuditEvent.model_validate_json(row["body"]) for row in rows]

    def list_project_events(self, project_id: str) -> list[ProjectAuditEvent]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT body FROM project_audit_events WHERE project_id = ? ORDER BY sequence",
                (project_id,),
            ).fetchall()
        return [ProjectAuditEvent.model_validate_json(row["body"]) for row in rows]

    def health(self) -> dict[str, int | str]:
        return self.validate_snapshot(self.path)
