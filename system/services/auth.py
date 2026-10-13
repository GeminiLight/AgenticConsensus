from __future__ import annotations

import math
import secrets
import sqlite3
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from threading import Lock
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict
from pwdlib import PasswordHash

from system.services.database import Database


AuthRole = Literal["admin", "operator", "viewer"]


@dataclass(frozen=True, repr=False)
class PasswordRecoveryPlan:
    user_id: str
    expected_password_hash: str
    new_password_hash: str
    event: AuthAuditEvent


@dataclass(frozen=True, repr=False)
class DevelopmentIdentity:
    actor: str
    username: str = "admin"
    password: str = "admin"


class AuthUser(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    username: str
    actor: str
    role: AuthRole
    disabled: bool
    password_change_required: bool
    created_at: datetime


class AuthenticatedSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user: AuthUser
    csrf_token: str
    expires_at: datetime


class AuthAuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    action: Literal[
        "auth_bootstrap",
        "auth_user_create",
        "auth_user_disable",
        "auth_user_enable",
        "auth_password_change",
        "auth_password_reset",
        "auth_password_recovery",
        "auth_sessions_revoke",
    ]
    actor: str
    target_user_id: str
    payload: dict[str, str]
    created_at: datetime


class AuthConflict(ValueError):
    pass


class AuthNotFound(KeyError):
    pass


class InvalidCurrentPassword(ValueError):
    pass


class LoginThrottle:
    """Bound repeated login attempts without persisting submitted credentials."""

    def __init__(self, *, max_failures: int = 5, window_seconds: int = 300):
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def retry_after(self, key: str) -> int | None:
        with self._lock:
            now = time.monotonic()
            attempts = self._failures.get(key)
            if attempts is None:
                return None
            while attempts and now - attempts[0] >= self.window_seconds:
                attempts.popleft()
            if not attempts:
                self._failures.pop(key, None)
                return None
            if len(attempts) < self.max_failures:
                return None
            return max(1, math.ceil(self.window_seconds - (now - attempts[0])))

    def record_failure(self, key: str) -> None:
        with self._lock:
            self._failures[key].append(time.monotonic())

    def clear(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


class AuthService:
    def __init__(self, database: Database, *, session_ttl_seconds: int = 8 * 60 * 60):
        if session_ttl_seconds < 60:
            raise ValueError("session TTL must be at least 60 seconds")
        self.database = database
        self.session_ttl = timedelta(seconds=session_ttl_seconds)
        self.password_hash = PasswordHash.recommended()
        self._dummy_hash = self.password_hash.hash(secrets.token_urlsafe(32))

    @staticmethod
    def normalize_identity(value: str, *, label: str) -> tuple[str, str]:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{label} cannot be empty")
        if any(ord(char) < 32 or ord(char) == 127 for char in normalized):
            raise ValueError(f"{label} contains control characters")
        if len(normalized) > 200:
            raise ValueError(f"{label} is too long")
        return normalized, normalized.casefold()

    @staticmethod
    def validate_password(password: str) -> None:
        if len(password) < 12:
            raise ValueError("password must contain at least 12 characters")
        if len(password.encode("utf-8")) > 1024:
            raise ValueError("password is too long")
        if "\x00" in password:
            raise ValueError("password contains a null byte")

    @staticmethod
    def _public_user(row: dict) -> AuthUser:
        return AuthUser(
            id=row["id"],
            username=row["username"],
            actor=row["actor"],
            role=row["role"],
            disabled=bool(row["disabled"]),
            password_change_required=bool(row.get("password_change_required", False)),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def setup_required(self) -> bool:
        return self.database.auth_user_count() == 0

    def _new_user_record(
        self,
        *,
        username: str,
        actor: str,
        password: str,
        role: AuthRole,
        password_change_required: bool,
        enforce_password_policy: bool = True,
    ) -> dict:
        canonical_username, normalized_username = self.normalize_identity(
            username, label="username"
        )
        canonical_actor, normalized_actor = self.normalize_identity(actor, label="actor")
        if enforce_password_policy:
            self.validate_password(password)
        now = datetime.now(UTC).isoformat()
        return {
            "id": f"user-{uuid4().hex[:16]}",
            "username": canonical_username,
            "username_normalized": normalized_username,
            "actor": canonical_actor,
            "actor_normalized": normalized_actor,
            "role": role,
            "password_hash": self.password_hash.hash(password),
            "disabled": False,
            "password_change_required": password_change_required,
            "created_at": now,
            "updated_at": now,
        }

    @staticmethod
    def _new_audit_event(
        *,
        action: Literal[
            "auth_bootstrap",
            "auth_user_create",
            "auth_user_disable",
            "auth_user_enable",
            "auth_password_change",
            "auth_password_reset",
            "auth_password_recovery",
            "auth_sessions_revoke",
        ],
        actor: str,
        target: dict,
    ) -> AuthAuditEvent:
        return AuthAuditEvent(
            id=f"auth-event-{uuid4().hex[:16]}",
            action=action,
            actor=actor,
            target_user_id=target["id"],
            payload={
                "target_actor": target["actor"],
                "target_role": target["role"],
            },
            created_at=datetime.now(UTC),
        )

    def bootstrap(self, *, username: str, actor: str, password: str) -> tuple[AuthUser, str, AuthenticatedSession]:
        record = self._new_user_record(
            username=username,
            actor=actor,
            password=password,
            role="admin",
            password_change_required=False,
        )
        event = self._new_audit_event(
            action="auth_bootstrap", actor=record["actor"], target=record
        )
        try:
            self.database.create_first_auth_user(
                record, event.model_dump(mode="json")
            )
        except (sqlite3.IntegrityError, ValueError) as exc:
            raise AuthConflict("authentication is already initialized") from exc
        return self._issue_session(record)

    def bootstrap_development(self, identity: DevelopmentIdentity) -> AuthUser:
        record = self._new_user_record(
            username=identity.username,
            actor=identity.actor,
            password=identity.password,
            role="admin",
            password_change_required=False,
            enforce_password_policy=False,
        )
        event = self._new_audit_event(
            action="auth_bootstrap", actor=record["actor"], target=record
        )
        try:
            self.database.create_first_auth_user(
                record, event.model_dump(mode="json")
            )
        except (sqlite3.IntegrityError, ValueError) as exc:
            raise AuthConflict("authentication is already initialized") from exc
        return self._public_user(record)

    def create_user(
        self,
        *,
        requester_actor: str,
        username: str,
        actor: str,
        password: str,
        role: AuthRole,
    ) -> AuthUser:
        record = self._new_user_record(
            username=username,
            actor=actor,
            password=password,
            role=role,
            password_change_required=True,
        )
        event = self._new_audit_event(
            action="auth_user_create", actor=requester_actor, target=record
        )
        try:
            self.database.create_auth_user(record, event.model_dump(mode="json"))
        except sqlite3.IntegrityError as exc:
            raise AuthConflict("username or actor is already registered") from exc
        return self._public_user(record)

    def signup(
        self, *, username: str, actor: str, password: str
    ) -> tuple[AuthUser, str, AuthenticatedSession]:
        record = self._new_user_record(
            username=username,
            actor=actor,
            password=password,
            role="operator",
            password_change_required=False,
        )
        event = self._new_audit_event(
            action="auth_user_create", actor=record["actor"], target=record
        )
        try:
            self.database.create_auth_user(record, event.model_dump(mode="json"))
        except sqlite3.IntegrityError as exc:
            raise AuthConflict("username or actor is already registered") from exc
        return self._issue_session(record)

    def list_users(self) -> list[AuthUser]:
        return [self._public_user(row) for row in self.database.list_auth_users()]

    def list_events(self) -> list[AuthAuditEvent]:
        return [AuthAuditEvent.model_validate(item) for item in self.database.list_auth_events()]

    def set_user_disabled(
        self,
        *,
        requester_id: str,
        requester_actor: str,
        user_id: str,
        disabled: bool,
    ) -> AuthUser:
        if requester_id == user_id and disabled:
            raise AuthConflict("the current administrator cannot disable their own account")
        target = self.database.get_auth_user(user_id)
        if target is None:
            raise AuthNotFound(user_id)
        event = self._new_audit_event(
            action="auth_user_disable" if disabled else "auth_user_enable",
            actor=requester_actor,
            target=target,
        )
        try:
            row = self.database.set_auth_user_disabled(
                user_id, disabled, event.model_dump(mode="json")
            )
        except ValueError as exc:
            raise AuthConflict(str(exc)) from exc
        if row is None:
            raise AuthNotFound(user_id)
        return self._public_user(row)

    def change_password(
        self, *, user_id: str, current_password: str, new_password: str
    ) -> tuple[AuthUser, str, AuthenticatedSession]:
        row = self.database.get_auth_user(user_id)
        if row is None or bool(row["disabled"]):
            raise AuthNotFound(user_id)
        try:
            current_verified = self.password_hash.verify(
                current_password, row["password_hash"]
            )
        except (TypeError, ValueError):
            current_verified = False
        if not current_verified:
            raise InvalidCurrentPassword("current password is incorrect")
        self.validate_password(new_password)
        try:
            reused = self.password_hash.verify(new_password, row["password_hash"])
        except (TypeError, ValueError):
            reused = False
        if reused:
            raise ValueError("new password must differ from current password")
        event = self._new_audit_event(
            action="auth_password_change", actor=row["actor"], target=row
        )
        try:
            updated, _ = self.database.replace_auth_password(
                user_id=user_id,
                expected_password_hash=row["password_hash"],
                password_hash=self.password_hash.hash(new_password),
                password_change_required=False,
                event=event.model_dump(mode="json"),
            )
        except ValueError as exc:
            raise AuthConflict(str(exc)) from exc
        return self._issue_session(updated)

    def reset_password(
        self,
        *,
        requester_id: str,
        requester_actor: str,
        user_id: str,
        new_password: str,
    ) -> AuthUser:
        if requester_id == user_id:
            raise AuthConflict(
                "administrators must use current-password verification for their own account"
            )
        row = self.database.get_auth_user(user_id)
        if row is None:
            raise AuthNotFound(user_id)
        self.validate_password(new_password)
        try:
            reused = self.password_hash.verify(new_password, row["password_hash"])
        except (TypeError, ValueError):
            reused = False
        if reused:
            raise ValueError("new password must differ from current password")
        event = self._new_audit_event(
            action="auth_password_reset", actor=requester_actor, target=row
        )
        try:
            updated, _ = self.database.replace_auth_password(
                user_id=user_id,
                expected_password_hash=row["password_hash"],
                password_hash=self.password_hash.hash(new_password),
                password_change_required=True,
                event=event.model_dump(mode="json"),
            )
        except KeyError as exc:
            raise AuthNotFound(user_id) from exc
        except ValueError as exc:
            raise AuthConflict(str(exc)) from exc
        return self._public_user(updated)

    def prepare_password_recovery(
        self,
        *,
        username: str,
        operator: str,
        reason: str,
        new_password: str,
    ) -> PasswordRecoveryPlan:
        """Validate and hash an offline recovery request without changing persistent state."""
        _, normalized_username = self.normalize_identity(username, label="username")
        canonical_operator, _ = self.normalize_identity(operator, label="operator")
        canonical_reason = reason.strip()
        if len(canonical_reason) < 8:
            raise ValueError("recovery reason must contain at least 8 characters")
        if len(canonical_reason) > 2000:
            raise ValueError("recovery reason is too long")
        if any(ord(char) < 32 and char not in "\n\t" for char in canonical_reason):
            raise ValueError("recovery reason contains control characters")

        row = self.database.get_auth_user_by_username(normalized_username)
        if row is None or bool(row["disabled"]):
            raise AuthNotFound(username)
        self.validate_password(new_password)
        try:
            reused = self.password_hash.verify(new_password, row["password_hash"])
        except (TypeError, ValueError):
            reused = False
        if reused:
            raise ValueError("new password must differ from current password")

        event = self._new_audit_event(
            action="auth_password_recovery",
            actor="local-maintenance",
            target=row,
        )
        event.payload["operator"] = canonical_operator
        event.payload["reason"] = canonical_reason
        return PasswordRecoveryPlan(
            user_id=row["id"],
            expected_password_hash=row["password_hash"],
            new_password_hash=self.password_hash.hash(new_password),
            event=event,
        )

    def recover_password(
        self, plan: PasswordRecoveryPlan
    ) -> tuple[AuthUser, AuthAuditEvent, int]:
        """Apply a prepared recovery from an exclusively locked maintenance process."""
        try:
            updated, revoked_sessions = self.database.replace_auth_password(
                user_id=plan.user_id,
                expected_password_hash=plan.expected_password_hash,
                password_hash=plan.new_password_hash,
                password_change_required=True,
                event=plan.event.model_dump(mode="json"),
            )
        except KeyError as exc:
            raise AuthNotFound(plan.user_id) from exc
        except ValueError as exc:
            raise AuthConflict(str(exc)) from exc
        plan.event.payload["revoked_sessions"] = str(revoked_sessions)
        return self._public_user(updated), plan.event, revoked_sessions

    def revoke_other_sessions(
        self, *, user_id: str, actor: str, current_raw_token: str
    ) -> int:
        row = self.database.get_auth_user(user_id)
        if row is None:
            raise AuthNotFound(user_id)
        event = self._new_audit_event(
            action="auth_sessions_revoke", actor=actor, target=row
        )
        try:
            return self.database.revoke_other_auth_sessions(
                user_id=user_id,
                current_token_hash=sha256(current_raw_token.encode("utf-8")).hexdigest(),
                event=event.model_dump(mode="json"),
            )
        except KeyError as exc:
            raise AuthNotFound(user_id) from exc

    def authenticate_password(self, *, username: str, password: str) -> dict | None:
        _, normalized_username = self.normalize_identity(username, label="username")
        row = self.database.get_auth_user_by_username(normalized_username)
        candidate_hash = row["password_hash"] if row is not None else self._dummy_hash
        try:
            verified, updated_hash = self.password_hash.verify_and_update(
                password, candidate_hash
            )
        except (TypeError, ValueError):
            verified = False
            updated_hash = None
        if row is None or not verified or bool(row["disabled"]):
            return None
        if updated_hash:
            self.database.update_auth_password_hash(row["id"], updated_hash)
        return row

    def login(self, *, username: str, password: str) -> tuple[AuthUser, str, AuthenticatedSession] | None:
        row = self.authenticate_password(username=username, password=password)
        return self._issue_session(row) if row is not None else None

    def _issue_session(self, user_row: dict) -> tuple[AuthUser, str, AuthenticatedSession]:
        raw_token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        created_at = datetime.now(UTC)
        expires_at = created_at + self.session_ttl
        self.database.create_auth_session(
            {
                "token_hash": sha256(raw_token.encode("utf-8")).hexdigest(),
                "user_id": user_row["id"],
                "csrf_token": csrf_token,
                "created_at": created_at.isoformat(),
                "expires_at": expires_at.isoformat(),
            }
        )
        user = self._public_user(user_row)
        return user, raw_token, AuthenticatedSession(
            user=user, csrf_token=csrf_token, expires_at=expires_at
        )

    def authenticate_session(self, raw_token: str | None) -> AuthenticatedSession | None:
        if not raw_token or len(raw_token) > 512:
            return None
        token_hash = sha256(raw_token.encode("utf-8")).hexdigest()
        row = self.database.get_auth_session(token_hash)
        if row is None:
            return None
        expires_at = datetime.fromisoformat(row["expires_at"])
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= datetime.now(UTC) or bool(row["disabled"]):
            self.database.delete_auth_session(token_hash)
            return None
        return AuthenticatedSession(
            user=self._public_user(row),
            csrf_token=row["csrf_token"],
            expires_at=expires_at,
        )

    def logout(self, raw_token: str | None) -> None:
        if raw_token and len(raw_token) <= 512:
            self.database.delete_auth_session(sha256(raw_token.encode("utf-8")).hexdigest())
