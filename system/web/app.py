from __future__ import annotations

import base64
import binascii
import hmac
import json
import os
import re
import secrets
import shutil
import statistics
import tempfile
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Literal

import httpx

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from system import __version__
from system.domain.ai import AIAdvisoryRun, AIEvalSummary
from system.domain.models import (
    AttestationTrustRoot,
    AuditEvent,
    AuthorityGrant,
    ContractGraph,
    DecisionAction,
    IntentMap,
    InterpretationCandidate,
    Project,
    RepositorySource,
    ReviewPackage,
    StructuralClaim,
    SourceReadingDraft,
)
from system.domain.transitions import DecisionBlocked
from system.paths import default_database_path
from system.services.auth import (
    AuthAuditEvent,
    AuthConflict,
    AuthNotFound,
    AuthRole,
    AuthService,
    AuthUser,
    AuthenticatedSession,
    DevelopmentIdentity,
    InvalidCurrentPassword,
    LoginThrottle,
)
from system.services.database import ConcurrentTransitionError, Database, RecordNotFound
from system.services.git_service import GitError, GitRepository
from system.services.github import (
    GitHubAppSetup,
    GitHubAuthorizationError,
    GitHubConnectionRequired,
    GitHubDisconnectResult,
    GitHubIntegrationError,
    GitHubNotConfigured,
    GitHubPullRequest,
    GitHubRepository,
    GitHubRepositoryAlreadyManaged,
    GitHubService,
    GitHubStatus,
)
from system.services.llm import EvidenceSummarizer, LLMConfig, SummaryResult
from system.services.commitment_ai import CommitmentAdvisor
from system.services.ai_copilot import ConsensusCopilot
from system.services.review_service import DuplicateProjectError, DuplicateReviewError, ReviewService


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    repo_path: str = Field(min_length=1, max_length=4096)
    repo_label: str | None = Field(default=None, max_length=240)
    head_ref: str = Field(default="HEAD", min_length=1, max_length=200)
    test_command: list[str] = Field(default_factory=list, max_length=64)
    claims: list[StructuralClaim] = Field(default_factory=list, max_length=100)
    policy_id: str = Field(default="local-single-user/v1", min_length=1, max_length=200)
    default_authority: str = Field(default="local operator", min_length=1, max_length=160)
    authority_grants: list[AuthorityGrant] = Field(default_factory=list, max_length=100)
    attestation_trust_roots: list[AttestationTrustRoot] = Field(default_factory=list, max_length=100)

    @field_validator("name", "repo_path", "head_ref", "policy_id", "default_authority")
    @classmethod
    def reject_blank_strings(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class PaperDemoDispatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1, max_length=2000)
    method: Literal["GET", "POST"] = "GET"
    body: dict | None = None
    snapshot: str | None = Field(default=None, max_length=900_000)

    @field_validator("path")
    @classmethod
    def local_case_path(cls, value: str) -> str:
        route = value.split("?", 1)[0]
        if not re.fullmatch(r"/api/(health|runtime|projects(?:/[a-zA-Z0-9_/-]+)?|reviews/[a-zA-Z0-9_/-]+)", route) or ".." in value or "//" in value or "\\" in value or "#" in value:
            raise ValueError("Only local StudyShare API paths are allowed")
        return value


class RepositoryTreeEntry(BaseModel):
    path: str
    name: str
    kind: Literal["directory", "file"]
    depth: int = Field(ge=0)


class ProjectTreeResponse(BaseModel):
    project_id: str
    ref: str
    revision: str
    entries: list[RepositoryTreeEntry]
    truncated: bool = False


class ProjectFileResponse(BaseModel):
    project_id: str
    revision: str
    path: str
    object_id: str
    byte_size: int | None
    byte_limit: int
    status: Literal["text", "empty", "binary", "too_large", "symlink", "submodule"]
    content: str | None


class GitHubOAuthStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    redirect_uri: str = Field(min_length=10, max_length=1000)


class GitHubAppSetupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin: str = Field(min_length=8, max_length=1000)


class ImportGitHubRepositoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    installation_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=160)
    test_command: list[str] = Field(default_factory=list, max_length=64)
    claims: list[StructuralClaim] = Field(default_factory=list, max_length=100)
    policy_id: str = Field(default="github-readonly/v1", min_length=1, max_length=200)
    default_authority: str = Field(default="repository owner", min_length=1, max_length=160)
    authority_grants: list[AuthorityGrant] = Field(default_factory=list, max_length=100)
    attestation_trust_roots: list[AttestationTrustRoot] = Field(default_factory=list, max_length=100)

    @field_validator("name", "policy_id", "default_authority")
    @classmethod
    def reject_blank_github_project_strings(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class GitHubPullReviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project: Project
    review: ReviewPackage
    pull_request: GitHubPullRequest
    project_created: bool
    review_reused: bool


class AdoptionMetrics(BaseModel):
    projects: int = Field(ge=0)
    projects_with_review: int = Field(ge=0)
    activation_rate: float = Field(ge=0, le=1)
    median_seconds_to_first_review: float | None = Field(default=None, ge=0)
    projects_with_second_review_within_7_days: int = Field(ge=0)


class CreateReviewRequest(BaseModel):
    base_ref: str = Field(min_length=1, max_length=200)
    target_ref: str = Field(min_length=1, max_length=200)
    proposer: str = Field(default="coding-agent", min_length=1, max_length=200)
    intent_summary: str = Field(default="", max_length=1200)


class ReviewRevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_ref: str = Field(min_length=1, max_length=200)
    expected_revision: int = Field(ge=1)


class CommitmentDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    request: str = Field(default="", max_length=8000)
    language: Literal["zh", "en"] = "en"


class RerunTestsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    test_command: list[str] = Field(min_length=1, max_length=64)

    @field_validator("test_command")
    @classmethod
    def reject_blank_command_parts(cls, value: list[str]) -> list[str]:
        normalized = [part.strip() for part in value]
        if any(not part for part in normalized):
            raise ValueError("test command parts must not be blank")
        return normalized


class CreateIntentRequest(BaseModel):
    request: str = Field(min_length=1, max_length=8000)
    context: str = Field(min_length=1, max_length=8000)
    base_ref: str = Field(min_length=1, max_length=200)
    candidates: list[InterpretationCandidate] = Field(min_length=2, max_length=20)


class ClarifyIntentRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    answer: str = Field(min_length=1, max_length=4000)
    retained_candidate_ids: list[str] = Field(min_length=1, max_length=20)
    eliminated_candidate_ids: list[str] = Field(default_factory=list, max_length=20)
    resolved_uncertainties: dict[str, list[str]] = Field(default_factory=dict)
    candidate_revisions: dict[str, InterpretationCandidate] = Field(default_factory=dict)
    added_candidates: list[InterpretationCandidate] = Field(default_factory=list, max_length=20)
    expected_revision: int = Field(ge=1)


class SelectIntentCandidateRequest(BaseModel):
    candidate_id: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=8, max_length=2000)
    expected_revision: int = Field(ge=1)


class RealizeIntentRequest(BaseModel):
    expected_revision: int = Field(ge=1)


class InterpretIntentAIRequest(BaseModel):
    request: str = Field(min_length=1, max_length=8000)
    context: str = Field(min_length=1, max_length=8000)
    base_ref: str = Field(min_length=1, max_length=200)

    @field_validator("request", "context", "base_ref")
    @classmethod
    def reject_blank_ai_intent_fields(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized


class ReviewCopilotRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    deliberate: bool = True

    @field_validator("question")
    @classmethod
    def reject_blank_question(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized


class AIFeedbackRequest(BaseModel):
    verdict: Literal["accepted", "edited", "rejected"]
    note: str = Field(default="", max_length=4000)
    edited_response: str | None = Field(default=None, max_length=12000)

    @model_validator(mode="after")
    def validate_edited_response(self):
        if self.verdict == "edited":
            if self.edited_response is None or not self.edited_response.strip():
                raise ValueError("edited feedback requires the edited response")
            self.edited_response = self.edited_response.strip()
        elif self.edited_response is not None:
            raise ValueError("only edited feedback may include an edited response")
        return self


class CommitmentProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str = Field(min_length=1, max_length=200)
    expected_revision: int = Field(ge=1)
    commitment_id: str | None = Field(default=None, max_length=200)
    request: str = Field(min_length=1, max_length=8000)
    reason: str = Field(min_length=8, max_length=4000)
    title: str = Field(min_length=1, max_length=240)
    statement: str = Field(min_length=1, max_length=4000)
    category: Literal["behavior", "interface", "dependency", "authority", "compatibility"]
    paths: list[str] = Field(min_length=1, max_length=100)
    verification: str = Field(min_length=8, max_length=2000)
    source_readings: list[SourceReadingDraft] | None = Field(default=None, max_length=12)


class AttachEvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor: str = Field(min_length=1, max_length=200)
    authority: str = Field(min_length=1, max_length=160)
    policy_id: str = Field(min_length=1, max_length=200)
    obligation_ids: list[str] = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=8, max_length=2000)
    provenance: str = Field(min_length=1, max_length=1000)

    @field_validator("actor", "authority", "policy_id", "summary", "provenance")
    @classmethod
    def strip_nonblank_values(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized


class AttachDSSEAttestationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    obligation_ids: list[str] = Field(min_length=1, max_length=100)
    envelope: dict


class TrustRootPossessionTemplateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_root: AttestationTrustRoot


class TrustRootChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["add", "revoke", "rotate"]
    actor: str = Field(min_length=1, max_length=200)
    authority: str = Field(min_length=1, max_length=160)
    policy_id: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=8, max_length=2000)
    expected_project_version: int = Field(ge=1)
    key_id: str | None = Field(default=None, min_length=1, max_length=200)
    new_root: AttestationTrustRoot | None = None
    new_key_proof: dict | None = None
    revocation_mode: Literal["prospective", "retroactive"] = "prospective"
    confirm_retroactive: bool = False

    @field_validator("actor", "authority", "policy_id", "reason")
    @classmethod
    def strip_nonblank_values(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_action_fields(self):
        if self.action == "add" and (self.new_root is None or self.new_key_proof is None):
            raise ValueError("add requires new_root and new_key_proof")
        if self.action == "revoke" and not self.key_id:
            raise ValueError("revoke requires key_id")
        if self.action == "rotate" and (
            not self.key_id or self.new_root is None or self.new_key_proof is None
        ):
            raise ValueError("rotate requires key_id, new_root, and new_key_proof")
        if (
            self.action in {"revoke", "rotate"}
            and self.revocation_mode == "retroactive"
            and not self.confirm_retroactive
        ):
            raise ValueError("retroactive revocation requires explicit confirmation")
        return self


class BootstrapAuthRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=200)
    actor: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=12, max_length=1024)


class SignupRequest(BootstrapAuthRequest):
    pass


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=1024)


class CreateUserRequest(BootstrapAuthRequest):
    role: AuthRole


class UpdateUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    disabled: bool


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=12, max_length=1024)


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_password: str = Field(min_length=12, max_length=1024)


class AuthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user: AuthUser
    csrf_token: str
    expires_at: datetime


class DevelopmentSessionCodec:
    """Issue stateless sessions only for an explicitly configured demo identity."""

    def __init__(
        self,
        identity: DevelopmentIdentity,
        secret: str,
        *,
        ttl_seconds: int,
    ) -> None:
        if len(secret) < 32:
            raise ValueError("development session secret must contain at least 32 characters")
        self.identity = identity
        self.secret = secret.encode("utf-8")
        self.ttl = timedelta(seconds=ttl_seconds)
        self.user = AuthUser(
            id="preview-demo-admin",
            username=identity.username,
            actor=identity.actor,
            role="admin",
            disabled=False,
            password_change_required=False,
            created_at=datetime.fromtimestamp(0, UTC),
        )

    @staticmethod
    def _encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    @staticmethod
    def _decode(value: str) -> bytes:
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(value + padding)

    def _signature(self, prefix: str, payload: str) -> str:
        return self._encode(
            hmac.new(
                self.secret,
                f"{prefix}.{payload}".encode("ascii"),
                sha256,
            ).digest()
        )

    def _pack(self, prefix: str, value: dict) -> str:
        payload = self._encode(
            json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
        )
        return f"{prefix}.{payload}.{self._signature(prefix, payload)}"

    def _unpack(self, raw_token: str | None, prefix: str) -> dict | None:
        if not raw_token:
            return None
        try:
            observed_prefix, payload, signature = raw_token.split(".", 2)
            if observed_prefix != prefix or not secrets.compare_digest(
                signature, self._signature(prefix, payload)
            ):
                return None
            decoded = json.loads(self._decode(payload))
        except (binascii.Error, json.JSONDecodeError, TypeError, ValueError):
            return None
        return decoded if isinstance(decoded, dict) else None

    def issue(self, user: AuthUser | None = None) -> tuple[str, AuthenticatedSession]:
        expires_at = datetime.now(UTC) + self.ttl
        csrf_token = secrets.token_urlsafe(32)
        session_user = user or self.user
        return (
            self._pack(
                "preview",
                {
                    "csrf": csrf_token,
                    "exp": int(expires_at.timestamp()),
                    "user": session_user.model_dump(mode="json"),
                },
            ),
            AuthenticatedSession(
                user=session_user,
                csrf_token=csrf_token,
                expires_at=expires_at,
            ),
        )

    def authenticate(self, raw_token: str | None) -> AuthenticatedSession | None:
        decoded = self._unpack(raw_token, "preview")
        if decoded is None:
            return None
        try:
            csrf_token = decoded["csrf"]
            expires_at = datetime.fromtimestamp(int(decoded["exp"]), UTC)
            user = AuthUser.model_validate(decoded["user"])
        except (KeyError, TypeError, ValueError):
            return None
        if (
            not isinstance(csrf_token, str)
            or not csrf_token
            or expires_at <= datetime.now(UTC)
        ):
            return None
        return AuthenticatedSession(
            user=user,
            csrf_token=csrf_token,
            expires_at=expires_at,
        )

    def issue_account(
        self, user: AuthUser, password: str
    ) -> tuple[str, datetime]:
        expires_at = datetime.now(UTC) + timedelta(days=30)
        return (
            self._pack(
                "account",
                {
                    "exp": int(expires_at.timestamp()),
                    "user": user.model_dump(mode="json"),
                    "verifier": self._credential_verifier(user.username, password),
                },
            ),
            expires_at,
        )

    def authenticate_account(
        self, username: str, password: str, raw_token: str | None
    ) -> AuthUser | None:
        decoded = self._unpack(raw_token, "account")
        if decoded is None:
            return None
        try:
            user = AuthUser.model_validate(decoded["user"])
            expires_at = datetime.fromtimestamp(int(decoded["exp"]), UTC)
            verifier = str(decoded["verifier"])
        except (KeyError, TypeError, ValueError):
            return None
        if expires_at <= datetime.now(UTC) or user.role != "operator":
            return None
        username_matches = secrets.compare_digest(
            username.strip().casefold(), user.username.casefold()
        )
        password_matches = secrets.compare_digest(
            verifier, self._credential_verifier(user.username, password)
        )
        return user if username_matches and password_matches else None

    def _credential_verifier(self, username: str, password: str) -> str:
        return self._encode(
            hmac.new(
                self.secret,
                f"account\0{username.casefold()}\0{password}".encode("utf-8"),
                sha256,
            ).digest()
        )


def deployment_app_options() -> dict[
    str, bool | str | Path | DevelopmentIdentity
]:
    """Return explicit hosting options without weakening the normal product mode."""
    if os.environ.get("VERCEL") != "1":
        return {}

    options: dict[str, bool | str | Path | DevelopmentIdentity] = {
        "database_path": Path("/tmp/agentic-consensus/agentic-consensus.db"),
        "secure_cookies": True,
    }
    if os.environ.get("AGENTIC_CONSENSUS_PAPER_DEMO", "").casefold() == "true":
        password = os.environ.get("AGENTIC_CONSENSUS_PAPER_DEMO_PASSWORD", "")
        secret = os.environ.get("AGENTIC_CONSENSUS_PAPER_DEMO_SECRET", "")
        if len(password) < 20 or len(secret) < 32:
            raise RuntimeError("paper demo requires private credentials and a signing secret")
        return {**options, "database_path": Path("/tmp/agentic-consensus-paper/paper.db"),
                "paper_demo": True,
                "development_identity": DevelopmentIdentity(actor="Research reviewer", username="reviewer", password=password),
                "development_session_secret": secret}
    preview_auth = (
        os.environ.get("AGENTIC_CONSENSUS_PREVIEW_DEVELOPMENT_AUTH", "").casefold()
        == "true"
    )
    if not preview_auth:
        return options
    if os.environ.get("VERCEL_ENV") != "preview":
        raise RuntimeError(
            "preview development authentication is forbidden outside Vercel Preview"
        )
    audit_identity = os.environ.get(
        "AGENTIC_CONSENSUS_PREVIEW_AUDIT_IDENTITY", ""
    ).strip()
    if not audit_identity:
        raise RuntimeError(
            "preview development authentication requires an audit identity"
        )
    session_secret = os.environ.get(
        "AGENTIC_CONSENSUS_PREVIEW_SESSION_SECRET", ""
    ).strip()
    if len(session_secret) < 32:
        raise RuntimeError(
            "preview development authentication requires a session signing secret"
        )
    options["development_identity"] = DevelopmentIdentity(actor=audit_identity)
    options["development_session_secret"] = session_secret
    options["allow_self_signup"] = (
        os.environ.get("AGENTIC_CONSENSUS_PREVIEW_SELF_SIGNUP", "").casefold()
        == "true"
    )
    return options


def create_app(
    database_path: str | Path | None = None,
    *,
    require_authentication: bool = True,
    secure_cookies: bool = False,
    session_ttl_seconds: int = 8 * 60 * 60,
    development_identity: DevelopmentIdentity | None = None,
    development_session_secret: str | None = None,
    allow_self_signup: bool = False,
    paper_demo: bool = False,
    paper_demo_dispatch: bool = True,
) -> FastAPI:
    if paper_demo and (not require_authentication or allow_self_signup or development_identity is None
                       or len(development_identity.password) < 20
                       or len(development_session_secret or "") < 32):
        raise ValueError("paper demo requires private credentials, authentication, and no self signup")
    database = Database(database_path or default_database_path())
    if paper_demo:
        from system.paper_demo import seed_paper_case
        seed_paper_case(database, Path(database_path or default_database_path()).parent / "studyshare")
    service = ReviewService(database)
    auth_service = AuthService(database, session_ttl_seconds=session_ttl_seconds)
    github_service = GitHubService(database)
    if development_identity is not None and auth_service.setup_required() and (not paper_demo or paper_demo_dispatch):
        auth_service.bootstrap_development(development_identity)
    development_session_codec = (
        DevelopmentSessionCodec(
            development_identity,
            development_session_secret,
            ttl_seconds=session_ttl_seconds,
        )
        if development_identity is not None and development_session_secret is not None
        else None
    )
    username_login_throttle = LoginThrottle()
    client_login_throttle = LoginThrottle(max_failures=20)
    paper_model_throttle = LoginThrottle(max_failures=8, window_seconds=60)
    summarizer = EvidenceSummarizer(LLMConfig.from_env())
    copilot = ConsensusCopilot(database, service, summarizer)
    commitment_advisor = CommitmentAdvisor(database, service, summarizer)
    app = FastAPI(title="AgenticConsensus", version=__version__)
    app.state.database = database
    app.state.review_service = service
    app.state.auth_service = auth_service
    app.state.github_service = github_service
    app.state.summarizer = summarizer
    app.state.copilot = copilot
    static_dir = Path(__file__).resolve().parent / "static"
    session_cookie_name = (
        "__Host-consensus_session" if secure_cookies else "consensus_session"
    )
    demo_account_cookie_name = (
        "__Host-consensus_demo_account" if secure_cookies else "consensus_demo_account"
    )
    bypass_session = AuthenticatedSession(
        user=AuthUser(
            id="test-auth-bypass",
            username="test-auth-bypass",
            actor="test-auth-bypass",
            role="admin",
            disabled=False,
            password_change_required=False,
            created_at=datetime.now(UTC),
        ),
        csrf_token="test-auth-bypass",
        expires_at=datetime.now(UTC),
    )

    @app.middleware("http")
    async def browser_security_headers(request: Request, call_next):
        if paper_demo and paper_demo_dispatch and request.url.path.startswith(("/api/projects", "/api/reviews")):
            return JSONResponse(status_code=409, content={"detail":"Open the workspace to use your temporary browser-session records."})
        if paper_demo and request.method not in {"GET", "HEAD", "OPTIONS"}:
            # This is a controlled synthetic case, not a public repository runner.
            path = request.url.path
            allowed = path in {"/api/auth/login", "/api/auth/logout", "/api/paper-demo/dispatch"} or re.fullmatch(
                r"/api/reviews/[^/]+/(commitment-draft|risk-analysis|commitments|revisions|evidence|decisions|tests)", path)
            if not allowed:
                return JSONResponse(status_code=403, content={"detail": "This research demo only supports the StudyShare review workflow."})
            if path.endswith(("/tests", "/revisions")):
                from system.paper_demo import FIXED, TEST_COMMAND
                try:
                    payload = await request.json()
                except ValueError:
                    payload = {}
                if not isinstance(payload, dict) or (path.endswith("/tests") and payload.get("test_command") != TEST_COMMAND) or (path.endswith("/revisions") and payload.get("target_ref") != FIXED):
                    return JSONResponse(status_code=403, content={"detail": "Only the bundled StudyShare revision and test command are allowed in this demo."})
            if path.endswith(("/commitment-draft", "/risk-analysis")):
                retry_after = paper_model_throttle.retry_after("paper-model")
                if retry_after:
                    return JSONResponse(status_code=429, headers={"Retry-After": str(retry_after)}, content={"detail": "Please wait before requesting more model advice."})
                paper_model_throttle.record_failure("paper-model")
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "base-uri 'none'; "
            "connect-src 'self'; "
            f"form-action 'self' {github_service.config.web_url}; "
            "frame-ancestors 'none'; "
            "img-src 'self' data:; "
            "object-src 'none'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'"
        )
        if request.url.path == "/" or request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        elif request.url.path.startswith("/static/") or request.url.path == "/entry.js":
            # Stable asset URLs must revalidate after a local upgrade. Otherwise
            # fresh templates can run stale scripts until a heuristic cache expires.
            response.headers["Cache-Control"] = "no-cache"
        if secure_cookies:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response

    def set_session_cookie(
        response: Response, raw_token: str, session: AuthenticatedSession
    ) -> None:
        max_age = max(0, int((session.expires_at - datetime.now(UTC)).total_seconds()))
        response.set_cookie(
            session_cookie_name,
            raw_token,
            max_age=max_age,
            expires=session.expires_at,
            path="/",
            secure=secure_cookies,
            httponly=True,
            samesite="strict",
        )

    def clear_session_cookie(response: Response) -> None:
        response.delete_cookie(
            session_cookie_name,
            path="/",
            secure=secure_cookies,
            httponly=True,
            samesite="strict",
        )

    def set_demo_account_cookie(
        response: Response, raw_token: str, expires_at: datetime
    ) -> None:
        max_age = max(0, int((expires_at - datetime.now(UTC)).total_seconds()))
        response.set_cookie(
            demo_account_cookie_name,
            raw_token,
            max_age=max_age,
            expires=expires_at,
            path="/",
            secure=secure_cookies,
            httponly=True,
            samesite="strict",
        )

    def current_session(request: Request) -> AuthenticatedSession:
        if not require_authentication:
            return bypass_session
        raw_token = request.cookies.get(session_cookie_name)
        session = (
            development_session_codec.authenticate(raw_token)
            if development_session_codec is not None
            else auth_service.authenticate_session(raw_token)
        )
        if session is None:
            raise HTTPException(status_code=401, detail="authentication required")
        return session

    def csrf_session(
        request: Request,
        session: AuthenticatedSession = Depends(current_session),
    ) -> AuthenticatedSession:
        if not require_authentication:
            return session
        supplied = request.headers.get("X-CSRF-Token", "")
        if not secrets.compare_digest(supplied, session.csrf_token):
            raise HTTPException(status_code=403, detail="valid CSRF token required")
        return session

    def product_session(
        session: AuthenticatedSession = Depends(current_session),
    ) -> AuthenticatedSession:
        if session.user.password_change_required:
            raise HTTPException(status_code=403, detail="password change required")
        return session

    def product_csrf_session(
        request: Request,
        session: AuthenticatedSession = Depends(product_session),
    ) -> AuthenticatedSession:
        if not require_authentication:
            return session
        supplied = request.headers.get("X-CSRF-Token", "")
        if not secrets.compare_digest(supplied, session.csrf_token):
            raise HTTPException(status_code=403, detail="valid CSRF token required")
        return session

    def operator_session(
        session: AuthenticatedSession = Depends(product_csrf_session),
    ) -> AuthenticatedSession:
        if session.user.role not in {"admin", "operator"}:
            raise HTTPException(status_code=403, detail="operator role required")
        return session

    def admin_session(
        session: AuthenticatedSession = Depends(product_csrf_session),
    ) -> AuthenticatedSession:
        if session.user.role != "admin":
            raise HTTPException(status_code=403, detail="administrator role required")
        return session

    def admin_read_session(
        session: AuthenticatedSession = Depends(product_session),
    ) -> AuthenticatedSession:
        if session.user.role != "admin":
            raise HTTPException(status_code=403, detail="administrator role required")
        return session

    def authenticated_actor(claimed_actor: str, session: AuthenticatedSession) -> str:
        if not require_authentication:
            return claimed_actor.strip()
        if claimed_actor.strip().casefold() != session.user.actor.casefold():
            raise HTTPException(
                status_code=403, detail="actor must match authenticated identity"
            )
        return session.user.actor

    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/entry.js", include_in_schema=False)
    def entry_script():
        return FileResponse(static_dir / "entry.js")

    @app.get("/", include_in_schema=False)
    def operator_console():
        if paper_demo:
            html = (static_dir / "index.html").read_text(encoding="utf-8")
            return HTMLResponse(html.replace('<html lang="zh-CN"', '<html lang="en" data-default-language="en" data-paper-demo="true"', 1))
        return FileResponse(static_dir / "index.html")

    @app.get("/api/health")
    def health():
        return database.health()

    @app.post("/api/paper-demo/dispatch")
    async def paper_dispatch(payload: PaperDemoDispatchRequest, request: Request,
                             session: AuthenticatedSession = Depends(operator_session)):
        if not paper_demo or not paper_demo_dispatch:
            raise HTTPException(status_code=404, detail="not found")
        from system.paper_demo import open_case, read_case_tables, restore_case_tables, seal_case
        secret = development_session_secret
        assert secret is not None
        try:
            tables = open_case(payload.snapshot, secret, session.csrf_token) if payload.snapshot else read_case_tables(database)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if payload.path.endswith(("/commitment-draft", "/risk-analysis")):
            retry_after = paper_model_throttle.retry_after("paper-model")
            if retry_after:
                raise HTTPException(status_code=429, detail="Please wait before requesting more model advice.", headers={"Retry-After":str(retry_after)})
            paper_model_throttle.record_failure("paper-model")
        # Each request gets an isolated database. The browser carries signed,
        # session-bound case records, never auth tables or provider credentials.
        with tempfile.TemporaryDirectory(prefix="consensus-paper-request-") as directory:
            transient = Database(Path(directory) / "case.db")
            repository = Path(database.path).parent / "studyshare"
            restore_case_tables(transient, tables, repository)
            inner = create_app(transient.path, secure_cookies=secure_cookies,
                development_identity=development_identity, development_session_secret=secret,
                paper_demo=True, paper_demo_dispatch=False)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=inner), base_url="https://paper-case.local") as client:
                response = await client.request(payload.method, payload.path, json=payload.body if payload.method == "POST" else None,
                    headers={"cookie":request.headers.get("cookie", ""), "X-CSRF-Token":session.csrf_token})
            try:
                snapshot = seal_case(transient, secret, session.csrf_token)
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            return JSONResponse(status_code=response.status_code, content={"result":response.json(), "snapshot":snapshot})

    @app.get("/api/adoption", response_model=AdoptionMetrics)
    def adoption_metrics(
        session: AuthenticatedSession = Depends(admin_read_session),
    ):
        del session
        projects = database.list_projects()
        first_review_seconds: list[float] = []
        activated = 0
        repeated_within_week = 0
        for project in projects:
            reviews = sorted(
                database.list_reviews(project.id), key=lambda item: item.created_at
            )
            if not reviews:
                continue
            activated += 1
            first_review_seconds.append(
                max(0.0, (reviews[0].created_at - project.created_at).total_seconds())
            )
            if (
                len(reviews) > 1
                and reviews[1].created_at - reviews[0].created_at <= timedelta(days=7)
            ):
                repeated_within_week += 1
        return AdoptionMetrics(
            projects=len(projects),
            projects_with_review=activated,
            activation_rate=(activated / len(projects) if projects else 0.0),
            median_seconds_to_first_review=(
                statistics.median(first_review_seconds) if first_review_seconds else None
            ),
            projects_with_second_review_within_7_days=repeated_within_week,
        )

    @app.get("/api/auth/state")
    def auth_state(request: Request):
        setup_required = auth_service.setup_required() and development_session_codec is None
        raw_token = request.cookies.get(session_cookie_name)
        session = (
            development_session_codec.authenticate(raw_token)
            if development_session_codec is not None
            else auth_service.authenticate_session(raw_token)
        )
        return {
            "setup_required": setup_required,
            **({"paper_demo": True} if paper_demo else {}),
            "signup_allowed": allow_self_signup and not setup_required,
            "authenticated": session is not None,
            "user": session.user if session else None,
            "csrf_token": session.csrf_token if session else None,
        }

    @app.post(
        "/api/auth/bootstrap",
        response_model=AuthResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def bootstrap_auth(request: BootstrapAuthRequest, response: Response):
        try:
            user, raw_token, session = auth_service.bootstrap(**request.model_dump())
        except AuthConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        set_session_cookie(response, raw_token, session)
        return AuthResponse(
            user=user,
            csrf_token=session.csrf_token,
            expires_at=session.expires_at,
        )

    @app.post(
        "/api/auth/signup",
        response_model=AuthResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def signup_auth(request_body: SignupRequest, response: Response):
        if not allow_self_signup:
            raise HTTPException(status_code=403, detail="self signup is disabled")
        if auth_service.setup_required():
            raise HTTPException(
                status_code=409,
                detail="the first administrator must be created before signup",
            )
        try:
            user, raw_token, session = auth_service.signup(
                **request_body.model_dump()
            )
        except AuthConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if development_session_codec is not None:
            raw_token, session = development_session_codec.issue(user)
            account_token, account_expires_at = (
                development_session_codec.issue_account(
                    user, request_body.password
                )
            )
            set_demo_account_cookie(response, account_token, account_expires_at)
        set_session_cookie(response, raw_token, session)
        return AuthResponse(
            user=user,
            csrf_token=session.csrf_token,
            expires_at=session.expires_at,
        )

    @app.post("/api/auth/login", response_model=AuthResponse)
    def login(request_body: LoginRequest, response: Response, request: Request):
        normalized_username = request_body.username.strip().casefold()
        client_host = request.client.host if request.client else "unknown"
        username_retry = username_login_throttle.retry_after(normalized_username)
        client_retry = client_login_throttle.retry_after(client_host)
        retry_after = max(
            value for value in (username_retry, client_retry) if value is not None
        ) if username_retry is not None or client_retry is not None else None
        if retry_after is not None:
            raise HTTPException(
                status_code=429,
                detail="too many login attempts",
                headers={"Retry-After": str(retry_after)},
            )
        if development_session_codec is not None and development_identity is not None:
            username_matches = secrets.compare_digest(
                normalized_username, development_identity.username.casefold()
            )
            password_matches = secrets.compare_digest(
                request_body.password, development_identity.password
            )
            if username_matches and password_matches:
                raw_token, session = development_session_codec.issue()
                result = (session.user, raw_token, session)
            else:
                account_user = development_session_codec.authenticate_account(
                    request_body.username,
                    request_body.password,
                    request.cookies.get(demo_account_cookie_name),
                )
                if account_user is not None:
                    raw_token, session = development_session_codec.issue(account_user)
                    result = (account_user, raw_token, session)
                else:
                    try:
                        database_result = auth_service.login(
                            **request_body.model_dump()
                        )
                    except ValueError:
                        database_result = None
                    if database_result is None:
                        result = None
                    else:
                        user, _, _ = database_result
                        raw_token, session = development_session_codec.issue(user)
                        result = (user, raw_token, session)
        else:
            try:
                result = auth_service.login(**request_body.model_dump())
            except ValueError:
                result = None
        if result is None:
            username_login_throttle.record_failure(normalized_username)
            client_login_throttle.record_failure(client_host)
            raise HTTPException(status_code=401, detail="invalid username or password")
        username_login_throttle.clear(normalized_username)
        user, raw_token, session = result
        set_session_cookie(response, raw_token, session)
        return AuthResponse(
            user=user,
            csrf_token=session.csrf_token,
            expires_at=session.expires_at,
        )

    @app.post("/api/auth/password", response_model=AuthResponse)
    def change_password(
        request_body: ChangePasswordRequest,
        request: Request,
        response: Response,
        current: AuthenticatedSession = Depends(csrf_session),
    ):
        try:
            user, raw_token, session = auth_service.change_password(
                user_id=current.user.id, **request_body.model_dump()
            )
        except InvalidCurrentPassword as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except AuthNotFound as exc:
            raise HTTPException(status_code=401, detail="authentication required") from exc
        except AuthConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        auth_service.logout(request.cookies.get(session_cookie_name))
        set_session_cookie(response, raw_token, session)
        return AuthResponse(
            user=user,
            csrf_token=session.csrf_token,
            expires_at=session.expires_at,
        )

    @app.post("/api/auth/sessions/revoke-others")
    def revoke_other_sessions(
        request: Request,
        current: AuthenticatedSession = Depends(csrf_session),
    ):
        raw_token = request.cookies.get(session_cookie_name)
        if not raw_token:
            raise HTTPException(status_code=401, detail="authentication required")
        try:
            revoked = auth_service.revoke_other_sessions(
                user_id=current.user.id,
                actor=current.user.actor,
                current_raw_token=raw_token,
            )
        except AuthNotFound as exc:
            raise HTTPException(status_code=401, detail="authentication required") from exc
        return {"revoked_sessions": revoked}

    @app.post("/api/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
    def logout(
        request: Request,
        response: Response,
        session: AuthenticatedSession = Depends(csrf_session),
    ):
        del session
        auth_service.logout(request.cookies.get(session_cookie_name))
        clear_session_cookie(response)

    @app.get("/api/users", response_model=list[AuthUser])
    def list_users(
        session: AuthenticatedSession = Depends(admin_read_session),
    ):
        del session
        return auth_service.list_users()

    @app.post("/api/users", response_model=AuthUser, status_code=status.HTTP_201_CREATED)
    def create_user(
        request: CreateUserRequest,
        session: AuthenticatedSession = Depends(admin_session),
    ):
        try:
            return auth_service.create_user(
                requester_actor=session.user.actor, **request.model_dump()
            )
        except AuthConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.patch("/api/users/{user_id}", response_model=AuthUser)
    def update_user(
        user_id: str,
        request: UpdateUserRequest,
        session: AuthenticatedSession = Depends(admin_session),
    ):
        try:
            return auth_service.set_user_disabled(
                requester_id=session.user.id,
                requester_actor=session.user.actor,
                user_id=user_id,
                disabled=request.disabled,
            )
        except AuthNotFound as exc:
            raise HTTPException(status_code=404, detail="user not found") from exc
        except AuthConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/users/{user_id}/password", response_model=AuthUser)
    def reset_user_password(
        user_id: str,
        request: ResetPasswordRequest,
        session: AuthenticatedSession = Depends(admin_session),
    ):
        try:
            return auth_service.reset_password(
                requester_id=session.user.id,
                requester_actor=session.user.actor,
                user_id=user_id,
                **request.model_dump(),
            )
        except AuthNotFound as exc:
            raise HTTPException(status_code=404, detail="user not found") from exc
        except AuthConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/auth/events", response_model=list[AuthAuditEvent])
    def list_auth_events(
        session: AuthenticatedSession = Depends(admin_read_session),
    ):
        del session
        return auth_service.list_events()

    @app.get("/api/runtime")
    def runtime_status(
        session: AuthenticatedSession = Depends(product_session),
    ):
        del session
        return summarizer.config.runtime_status()

    @app.get("/api/github/status", response_model=GitHubStatus)
    def github_status(
        session: AuthenticatedSession = Depends(product_session),
    ):
        return github_service.status(
            session.user.id,
            setup_allowed=session.user.role == "admin",
            connection_allowed=session.user.role in {"admin", "operator"},
        )

    @app.post("/api/github/app/setup/start", response_model=GitHubAppSetup)
    def begin_github_app_setup(
        request: GitHubAppSetupRequest,
        session: AuthenticatedSession = Depends(admin_session),
    ):
        try:
            return github_service.begin_app_setup(
                user_id=session.user.id,
                origin=request.origin,
            )
        except GitHubIntegrationError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/github/app/setup/callback", include_in_schema=False)
    def complete_github_app_setup(code: str = "", state: str = "", error: str = ""):
        if error:
            raise HTTPException(status_code=400, detail="GitHub App setup was cancelled")
        try:
            authorization = github_service.complete_app_setup(code=code, state=state)
        except GitHubAuthorizationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except GitHubIntegrationError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return RedirectResponse(url=authorization["authorization_url"], status_code=303)

    @app.post("/api/github/oauth/start")
    def begin_github_oauth(
        request: GitHubOAuthStartRequest,
        session: AuthenticatedSession = Depends(operator_session),
    ):
        try:
            return github_service.begin_authorization(
                user_id=session.user.id, redirect_uri=request.redirect_uri
            )
        except GitHubNotConfigured as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/github/oauth/callback", include_in_schema=False)
    def complete_github_oauth(code: str = "", state: str = "", error: str = ""):
        if error:
            raise HTTPException(status_code=400, detail="GitHub authorization was cancelled")
        try:
            user_id = github_service.complete_authorization(code=code, state=state)
        except GitHubNotConfigured as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except GitHubAuthorizationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            if not github_service.has_installations(user_id):
                return RedirectResponse(url=github_service.install_url(), status_code=303)
        except GitHubIntegrationError:
            pass
        return RedirectResponse(url="/?github=connected", status_code=303)

    @app.get("/api/github/repositories", response_model=list[GitHubRepository])
    def list_github_repositories(
        session: AuthenticatedSession = Depends(product_session),
    ):
        try:
            return github_service.list_repositories(session.user.id)
        except GitHubConnectionRequired as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except GitHubAuthorizationError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except GitHubIntegrationError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.get(
        "/api/github/repositories/{repository_id}/pulls",
        response_model=list[GitHubPullRequest],
    )
    def list_github_pull_requests(
        repository_id: int,
        installation_id: int,
        session: AuthenticatedSession = Depends(product_session),
    ):
        try:
            repository = github_service.get_repository(
                session.user.id,
                installation_id=installation_id,
                repository_id=repository_id,
            )
            return github_service.list_pull_requests(session.user.id, repository)
        except GitHubConnectionRequired as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except GitHubAuthorizationError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except GitHubIntegrationError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post(
        "/api/github/repositories/{repository_id}/pulls/{pull_number}/analyze",
        response_model=GitHubPullReviewResult,
        status_code=status.HTTP_201_CREATED,
    )
    def analyze_github_pull_request(
        repository_id: int,
        pull_number: int,
        request: ImportGitHubRepositoryRequest,
        response: Response,
        session: AuthenticatedSession = Depends(operator_session),
    ):
        checkout: Path | None = None
        project: Project | None = None
        project_created = False
        try:
            repository = github_service.get_repository(
                session.user.id,
                installation_id=request.installation_id,
                repository_id=repository_id,
            )
            pull_request = github_service.get_pull_request(
                session.user.id, repository, pull_number
            )
            project = database.find_project_by_github_repository(repository.id)
            if project is None:
                checkout = github_service.clone_repository(session.user.id, repository)
                base_ref, target_ref = github_service.fetch_pull_request(
                    session.user.id, repository, pull_request, checkout
                )
                source = RepositorySource(
                    repository_id=repository.id,
                    installation_id=repository.installation_id,
                    full_name=repository.full_name,
                    html_url=repository.html_url,
                    default_branch=repository.default_branch,
                    visibility=repository.visibility,
                    connected_by=session.user.actor,
                )
                project = service.create_project(
                    name=request.name,
                    repo_path=checkout,
                    repo_label=f"github://{repository.full_name}",
                    head_ref="HEAD",
                    test_command=request.test_command,
                    claims=request.claims,
                    policy_id=request.policy_id,
                    default_authority=request.default_authority,
                    authority_grants=request.authority_grants,
                    attestation_trust_roots=request.attestation_trust_roots,
                    source=source,
                )
                project_created = True
            else:
                base_ref, target_ref = github_service.fetch_pull_request(
                    session.user.id, repository, pull_request, project.repo_path
                )
            review_reused = False
            try:
                review = service.create_review(
                    project.id,
                    base_ref=base_ref,
                    target_ref=target_ref,
                    proposer=f"github:@{pull_request.author}",
                    intent_summary=pull_request.title,
                    external_url=pull_request.html_url,
                    external_label=f"GitHub PR #{pull_request.number}",
                )
            except DuplicateReviewError:
                review = next(
                    item
                    for item in database.list_reviews(project.id)
                    if item.base_ref == base_ref and item.target_ref == target_ref
                )
                review_reused = True
                response.status_code = status.HTTP_200_OK
            return GitHubPullReviewResult(
                project=project,
                review=review,
                pull_request=pull_request,
                project_created=project_created,
                review_reused=review_reused,
            )
        except GitHubConnectionRequired as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except GitHubAuthorizationError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except DuplicateProjectError as exc:
            if checkout is not None and not project_created:
                shutil.rmtree(checkout, ignore_errors=True)
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (GitHubIntegrationError, GitError, ValueError) as exc:
            if checkout is not None and not project_created:
                shutil.rmtree(checkout, ignore_errors=True)
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post(
        "/api/github/repositories/{repository_id}/import",
        response_model=Project,
        status_code=status.HTTP_201_CREATED,
    )
    def import_github_repository(
        repository_id: int,
        request: ImportGitHubRepositoryRequest,
        session: AuthenticatedSession = Depends(operator_session),
    ):
        checkout: Path | None = None
        try:
            repository = github_service.get_repository(
                session.user.id,
                installation_id=request.installation_id,
                repository_id=repository_id,
            )
            checkout = github_service.clone_repository(session.user.id, repository)
            source = RepositorySource(
                repository_id=repository.id,
                installation_id=repository.installation_id,
                full_name=repository.full_name,
                html_url=repository.html_url,
                default_branch=repository.default_branch,
                visibility=repository.visibility,
                connected_by=session.user.actor,
            )
            return service.create_project(
                name=request.name,
                repo_path=checkout,
                repo_label=f"github://{repository.full_name}",
                head_ref="HEAD",
                test_command=request.test_command,
                claims=request.claims,
                policy_id=request.policy_id,
                default_authority=request.default_authority,
                authority_grants=request.authority_grants,
                attestation_trust_roots=request.attestation_trust_roots,
                source=source,
            )
        except GitHubRepositoryAlreadyManaged as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except GitHubConnectionRequired as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except GitHubAuthorizationError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except DuplicateProjectError as exc:
            if checkout is not None:
                shutil.rmtree(checkout, ignore_errors=True)
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (GitHubIntegrationError, GitError, ValueError) as exc:
            if checkout is not None:
                shutil.rmtree(checkout, ignore_errors=True)
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.delete("/api/github/connection", response_model=GitHubDisconnectResult)
    def disconnect_github(
        session: AuthenticatedSession = Depends(operator_session),
    ):
        return github_service.disconnect(session.user.id)

    @app.get("/api/projects", response_model=list[Project])
    def list_projects(
        session: AuthenticatedSession = Depends(product_session),
    ):
        del session
        return database.list_projects()

    @app.post("/api/projects", response_model=Project, status_code=status.HTTP_201_CREATED)
    def create_project(
        request: CreateProjectRequest,
        session: AuthenticatedSession = Depends(operator_session),
    ):
        del session
        try:
            return service.create_project(**request.model_dump())
        except DuplicateProjectError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (GitError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/projects/{project_id}/file", response_model=ProjectFileResponse)
    def get_project_file(
        project_id: str,
        path: str = Query(min_length=1, max_length=1000),
        revision: str = Query(min_length=40, max_length=64),
        session: AuthenticatedSession = Depends(product_session),
    ):
        del session
        try:
            project = database.get_project(project_id)
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail="project not found") from exc
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", revision):
            raise HTTPException(status_code=422, detail="use the full snapshot commit ID")
        try:
            repository = GitRepository(project.repo_path)
            if repository.resolve(project.head_ref) != revision:
                raise HTTPException(status_code=409, detail="The project snapshot changed. Refresh the file list before opening a file.")
            return ProjectFileResponse(project_id=project_id, **repository.snapshot_file(revision, path))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="file is not tracked at this snapshot") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except GitError as exc:
            raise HTTPException(status_code=422, detail="The Git snapshot is unavailable. Check repository access and retry.") from exc

    @app.get("/api/projects/{project_id}/tree", response_model=ProjectTreeResponse)
    def get_project_tree(
        project_id: str,
        session: AuthenticatedSession = Depends(product_session),
    ):
        del session
        try:
            project = database.get_project(project_id)
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail="project not found") from exc
        try:
            revision, paths, truncated = GitRepository(project.repo_path).tracked_paths(
                project.head_ref
            )
        except GitError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        directories: set[str] = set()
        for path in paths:
            parts = Path(path).parts
            directories.update("/".join(parts[:index]) for index in range(1, len(parts)))
        entries = [
            RepositoryTreeEntry(
                path=path,
                name=Path(path).name,
                kind="directory",
                depth=len(Path(path).parts) - 1,
            )
            for path in directories
        ]
        entries.extend(
            RepositoryTreeEntry(
                path=path,
                name=Path(path).name,
                kind="file",
                depth=len(Path(path).parts) - 1,
            )
            for path in paths
        )
        entries.sort(key=lambda item: (item.path.casefold(), item.kind == "file"))
        return ProjectTreeResponse(
            project_id=project.id,
            ref=project.head_ref,
            revision=revision,
            entries=entries,
            truncated=truncated,
        )

    @app.post("/api/projects/{project_id}/trust-roots/changes", response_model=Project)
    def change_trust_roots(
        project_id: str,
        request: TrustRootChangeRequest,
        session: AuthenticatedSession = Depends(operator_session),
    ):
        try:
            payload = request.model_dump()
            payload["actor"] = authenticated_actor(request.actor, session)
            return service.change_trust_roots(project_id, **payload)
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail="project not found") from exc
        except DecisionBlocked as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/projects/{project_id}/trust-roots/possession-template")
    def build_trust_root_possession_template(
        project_id: str,
        request: TrustRootPossessionTemplateRequest,
        session: AuthenticatedSession = Depends(operator_session),
    ):
        del session
        try:
            return service.build_trust_root_possession_template(
                project_id, new_root=request.new_root
            )
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail="project not found") from exc
        except DecisionBlocked as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/projects/{project_id}/events")
    def list_project_events(
        project_id: str,
        session: AuthenticatedSession = Depends(product_session),
    ):
        del session
        try:
            database.get_project(project_id)
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail="project not found") from exc
        return database.list_project_events(project_id)

    @app.get("/api/projects/{project_id}/reviews", response_model=list[ReviewPackage])
    def list_reviews(
        project_id: str,
        session: AuthenticatedSession = Depends(product_session),
    ):
        del session
        try:
            database.get_project(project_id)
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail="project not found") from exc
        return database.list_reviews(project_id)

    @app.get("/api/projects/{project_id}/intents", response_model=list[IntentMap])
    def list_intents(
        project_id: str,
        session: AuthenticatedSession = Depends(product_session),
    ):
        del session
        try:
            database.get_project(project_id)
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail="project not found") from exc
        return database.list_intents(project_id)

    @app.post(
        "/api/projects/{project_id}/intents",
        response_model=IntentMap,
        status_code=status.HTTP_201_CREATED,
    )
    def create_intent(
        project_id: str,
        request: CreateIntentRequest,
        session: AuthenticatedSession = Depends(operator_session),
    ):
        try:
            return service.create_intent(
                project_id,
                **request.model_dump(),
                created_by=session.user.actor,
            )
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail="project not found") from exc
        except GitError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/intents/{intent_id}", response_model=IntentMap)
    def get_intent(
        intent_id: str,
        session: AuthenticatedSession = Depends(product_session),
    ):
        del session
        try:
            return database.get_intent(intent_id)
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail="intent not found") from exc

    @app.post("/api/intents/{intent_id}/clarifications", response_model=IntentMap)
    def clarify_intent(
        intent_id: str,
        request: ClarifyIntentRequest,
        session: AuthenticatedSession = Depends(operator_session),
    ):
        try:
            return service.clarify_intent(
                intent_id,
                **request.model_dump(),
                actor=session.user.actor,
            )
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail="intent not found") from exc
        except DecisionBlocked as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/intents/{intent_id}/selection", response_model=IntentMap)
    def select_intent_candidate(
        intent_id: str,
        request: SelectIntentCandidateRequest,
        session: AuthenticatedSession = Depends(operator_session),
    ):
        try:
            return service.select_intent_candidate(
                intent_id,
                **request.model_dump(),
                actor=session.user.actor,
            )
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail="intent not found") from exc
        except DecisionBlocked as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/intents/{intent_id}/realization", response_model=IntentMap)
    def realize_intent(
        intent_id: str,
        request: RealizeIntentRequest,
        session: AuthenticatedSession = Depends(operator_session),
    ):
        try:
            return service.realize_intent(
                intent_id,
                expected_revision=request.expected_revision,
                actor=session.user.actor,
            )
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail="intent not found") from exc
        except DecisionBlocked as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except GitError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post(
        "/api/projects/{project_id}/reviews",
        response_model=ReviewPackage,
        status_code=status.HTTP_201_CREATED,
    )
    def create_review(
        project_id: str,
        request: CreateReviewRequest,
        session: AuthenticatedSession = Depends(operator_session),
    ):
        del session
        try:
            return service.create_review(project_id, **request.model_dump())
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail="project not found") from exc
        except DuplicateReviewError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except GitError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post(
        "/api/projects/{project_id}/ai/interpret-intent",
        response_model=AIAdvisoryRun,
    )
    def interpret_intent_with_ai(
        project_id: str,
        request: InterpretIntentAIRequest,
        session: AuthenticatedSession = Depends(operator_session),
    ):
        try:
            return copilot.interpret_intent(
                project_id,
                **request.model_dump(),
                actor=session.user.actor,
            )
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail="project not found") from exc
        except ConcurrentTransitionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/reviews/{review_id}", response_model=ReviewPackage)
    def get_review(
        review_id: str,
        session: AuthenticatedSession = Depends(product_session),
    ):
        del session
        try:
            return database.get_review(review_id)
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail="review not found") from exc

    @app.post(
        "/api/reviews/{review_id}/ai/copilot",
        response_model=AIAdvisoryRun,
    )
    def ask_review_copilot(
        review_id: str,
        request: ReviewCopilotRequest,
        session: AuthenticatedSession = Depends(operator_session),
    ):
        try:
            return copilot.ask_review(
                review_id,
                question=request.question,
                deliberate=request.deliberate,
                actor=session.user.actor,
            )
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail="review not found") from exc
        except ConcurrentTransitionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post(
        "/api/reviews/{review_id}/ai/evidence-gaps",
        response_model=AIAdvisoryRun,
    )
    def plan_review_evidence_gaps(
        review_id: str,
        session: AuthenticatedSession = Depends(operator_session),
    ):
        try:
            return copilot.plan_evidence_gaps(review_id, actor=session.user.actor)
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail="review not found") from exc
        except ConcurrentTransitionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get(
        "/api/projects/{project_id}/ai/runs",
        response_model=list[AIAdvisoryRun],
    )
    def list_project_ai_runs(
        project_id: str,
        session: AuthenticatedSession = Depends(product_session),
    ):
        del session
        try:
            database.get_project(project_id)
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail="project not found") from exc
        return database.list_ai_runs(project_id=project_id)

    @app.get(
        "/api/projects/{project_id}/ai/evals",
        response_model=AIEvalSummary,
    )
    def project_ai_evals(
        project_id: str,
        session: AuthenticatedSession = Depends(product_session),
    ):
        del session
        try:
            return copilot.eval_summary(project_id)
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail="project not found") from exc

    @app.post("/api/ai/runs/{run_id}/feedback", response_model=AIAdvisoryRun)
    def record_ai_feedback(
        run_id: str,
        request: AIFeedbackRequest,
        session: AuthenticatedSession = Depends(operator_session),
    ):
        try:
            return copilot.record_feedback(
                run_id,
                **request.model_dump(),
                actor=session.user.actor,
            )
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail="AI advisory run not found") from exc

    @app.get("/api/reviews/{review_id}/graph", response_model=ContractGraph)
    def get_contract_graph(
        review_id: str,
        session: AuthenticatedSession = Depends(product_session),
    ):
        del session
        try:
            return service.get_contract_graph(review_id)
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail="review not found") from exc

    @app.get("/api/reviews/{review_id}/diff")
    def get_review_diff(
        review_id: str,
        session: AuthenticatedSession = Depends(product_session),
    ):
        del session
        try:
            return service.get_diff(review_id)
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail="review not found") from exc
        except GitError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/reviews/{review_id}/package")
    def get_change_package(
        review_id: str,
        session: AuthenticatedSession = Depends(product_session),
    ):
        del session
        try:
            return service.get_change_package(review_id)
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail="review not found") from exc

    @app.post("/api/reviews/{review_id}/revisions", response_model=ReviewPackage, status_code=201)
    def revise_review(review_id: str, request: ReviewRevisionRequest, session: AuthenticatedSession = Depends(operator_session)):
        try:
            return service.revise_review(review_id, **request.model_dump(), actor=session.user.actor if session else "local operator")
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail="review not found") from exc
        except (DecisionBlocked, DuplicateReviewError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (ValueError, GitError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/reviews/{review_id}/commitment-draft")
    def draft_review_commitment(review_id: str, request: CommitmentDraftRequest, session: AuthenticatedSession = Depends(operator_session)):
        try:
            return commitment_advisor.analyze(review_id, **request.model_dump(), actor=session.user.actor)
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail="review not found") from exc
        except (DecisionBlocked, ConcurrentTransitionError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (ValueError, GitError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/reviews/{review_id}/risk-analysis")
    def analyze_review_risks(review_id: str, request: CommitmentDraftRequest, session: AuthenticatedSession = Depends(operator_session)):
        try:
            return commitment_advisor.analyze(review_id, **request.model_dump(), actor=session.user.actor, feature="risk_analysis")
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail="review not found") from exc
        except (DecisionBlocked, ConcurrentTransitionError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (ValueError, GitError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/reviews/{review_id}/commitments", response_model=ReviewPackage)
    def propose_review_commitment(review_id: str, request: CommitmentProposalRequest,
        session: AuthenticatedSession = Depends(operator_session)):
        try:
            payload = request.model_dump()
            payload["actor"] = authenticated_actor(request.actor, session)
            return service.propose_commitment(review_id, **payload)
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail="review not found") from exc
        except DecisionBlocked as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/reviews/{review_id}/evidence", response_model=ReviewPackage)
    def attach_evidence(
        review_id: str,
        request: AttachEvidenceRequest,
        session: AuthenticatedSession = Depends(operator_session),
    ):
        try:
            payload = request.model_dump()
            payload["actor"] = authenticated_actor(request.actor, session)
            return service.attach_evidence(review_id, **payload)
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail="review not found") from exc
        except DecisionBlocked as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/reviews/{review_id}/tests", response_model=ReviewPackage)
    def rerun_review_tests(
        review_id: str,
        request: RerunTestsRequest,
        session: AuthenticatedSession = Depends(operator_session),
    ):
        try:
            return service.rerun_tests(
                review_id,
                test_command=request.test_command,
                actor=session.user.actor,
            )
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail="review not found") from exc
        except DecisionBlocked as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ConcurrentTransitionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/reviews/{review_id}/attestations/dsse", response_model=ReviewPackage)
    def attach_dsse_attestation(
        review_id: str,
        request: AttachDSSEAttestationRequest,
        session: AuthenticatedSession = Depends(operator_session),
    ):
        del session
        try:
            return service.attach_dsse_attestation(review_id, **request.model_dump())
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail="review not found") from exc
        except DecisionBlocked as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/reviews/{review_id}/export", response_class=JSONResponse)
    def export_change_package(
        review_id: str,
        session: AuthenticatedSession = Depends(product_session),
    ):
        del session
        try:
            review = database.get_review(review_id)
            project = database.get_project(review.project_id)
            manifest = service.get_change_package(review_id)
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail="review not found") from exc
        safe_project = project.model_dump(mode="json", exclude={"repo_path"})
        safe_project["repo_label"] = project.repo_label or "registered://local-repository"
        payload = {
            "format": "agentic-consensus/change-package@0.7",
            "exported_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "project": safe_project,
            "manifest": manifest,
            "review": review,
            "audit_events": database.list_events(review_id),
            "project_audit_events": database.list_project_events(project.id),
            "ai_advisory_runs": database.list_ai_runs(review_id=review_id, limit=500),
        }
        return JSONResponse(
            content=jsonable_encoder(payload),
            headers={
                "Content-Disposition": f'attachment; filename="{review.id}-change-package.json"',
                "Cache-Control": "no-store",
            },
        )

    @app.get("/api/reviews/{review_id}/events")
    def list_events(
        review_id: str,
        session: AuthenticatedSession = Depends(product_session),
    ):
        del session
        try:
            database.get_review(review_id)
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail="review not found") from exc
        return database.list_events(review_id)

    @app.post("/api/reviews/{review_id}/decisions", response_model=ReviewPackage)
    def make_decision(
        review_id: str,
        action: DecisionAction,
        session: AuthenticatedSession = Depends(operator_session),
    ):
        try:
            actor = authenticated_actor(action.actor, session)
            return service.decide(review_id, action.model_copy(update={"actor": actor}))
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail="review not found") from exc
        except DecisionBlocked as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/reviews/{review_id}/summary", response_model=SummaryResult)
    def summarize_review(
        review_id: str,
        session: AuthenticatedSession = Depends(operator_session),
    ):
        del session
        try:
            review = database.get_review(review_id)
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail="review not found") from exc
        tests = next((item.status for item in review.evidence if item.kind == "tests"), "missing")
        result = summarizer.summarize(
            {
                "patch_summary": review.patch_summary,
                "tests": tests,
                "findings": [item.model_dump(mode="json") for item in review.findings],
                "evidence": [item.model_dump(mode="json") for item in review.evidence],
            }
        )
        review.summary = result.summary
        expected_review_revision = review.revision
        review.revision += 1
        review.updated_at = datetime.now(UTC)
        event = AuditEvent(
            review_id=review.id,
            action="summarize",
            actor="system",
            payload={
                "source": result.source,
                "provider": result.provider,
                "model": result.model,
                "latency_ms": result.latency_ms,
                "usage": result.usage,
            },
        )
        try:
            database.apply_review_transition(
                review=review,
                event=event,
                expected_review_revision=expected_review_revision,
            )
        except ConcurrentTransitionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return result

    return app


app = create_app(**deployment_app_options())
