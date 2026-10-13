from __future__ import annotations

import base64
import binascii
from datetime import UTC, datetime
from hashlib import sha256
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


DecisionKind = Literal["commit", "waive", "rebase", "reject", "rollback"]
GovernedAction = Literal[
    "commit", "waive", "rebase", "reject", "rollback", "attest", "manage_trust"
]


def stable_obligation_id(claim_id: str, label: str) -> str:
    normalized_label = " ".join(label.split())
    digest = sha256(f"{claim_id}\0{normalized_label}".encode()).hexdigest()[:12]
    return f"obligation-{digest}"


class ArtifactAnchor(BaseModel):
    path: str
    kind: Literal["code", "config", "schema", "runtime", "test"] = "code"
    relation: Literal["realizes", "contests", "observes", "validates"] = "realizes"
    line: int | None = None
    version_ref: str | None = None


class EvidenceObligation(BaseModel):
    id: str
    claim_id: str
    # Commitment verification plans use this field across save and follow-up.
    # Keep the same bound as ProjectCommitment.verification; never drop checks.
    label: str = Field(min_length=1, max_length=2000)
    evidence_kind: Literal["attestation"] = "attestation"
    verification: Literal["authorized_record", "dsse_ed25519"] = "authorized_record"
    required_provenance_prefix: str | None = Field(default=None, min_length=1, max_length=500)
    required_verifier_id: str | None = Field(default=None, min_length=1, max_length=500)
    required_verified_level: str | None = Field(default=None, min_length=1, max_length=200)
    waivable: bool = True

    @model_validator(mode="after")
    def require_dsse_policy(self):
        if self.verification == "dsse_ed25519":
            if not self.required_verifier_id:
                raise ValueError("DSSE evidence obligations require required_verifier_id")
            if not self.required_verified_level:
                raise ValueError("DSSE evidence obligations require required_verified_level")
        return self


class AttestationTrustRoot(BaseModel):
    key_id: str = Field(min_length=1, max_length=200)
    algorithm: Literal["ed25519"] = "ed25519"
    public_key_base64: str = Field(min_length=1, max_length=500)
    verifier_id: str = Field(min_length=1, max_length=500)
    authority: str = Field(min_length=1, max_length=160)
    resource_uri_prefix: str = Field(min_length=1, max_length=1000)
    predicate_types: list[str] = Field(
        default_factory=lambda: ["https://slsa.dev/verification_summary/v1"],
        min_length=1,
        max_length=20,
    )
    status: Literal["active", "revoked"] = "active"
    valid_from: datetime = Field(default_factory=lambda: datetime.now(UTC))
    valid_until: datetime | None = None
    added_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    added_by: str = Field(default="project-registration", min_length=1, max_length=200)
    added_under_policy: str = Field(default="project-registration", min_length=1, max_length=200)
    revoked_at: datetime | None = None
    revoked_by: str | None = Field(default=None, min_length=1, max_length=200)
    revoked_under_policy: str | None = Field(default=None, min_length=1, max_length=200)
    revocation_reason: str | None = Field(default=None, min_length=8, max_length=2000)
    revocation_mode: Literal["prospective", "retroactive"] | None = None

    @field_validator("public_key_base64")
    @classmethod
    def validate_ed25519_public_key(cls, value: str) -> str:
        normalized = "".join(value.split())
        try:
            decoded = base64.b64decode(normalized, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("Ed25519 public key must be valid base64") from exc
        if len(decoded) != 32:
            raise ValueError("Ed25519 public key must decode to exactly 32 bytes")
        return normalized

    @model_validator(mode="after")
    def validate_lifecycle(self):
        valid_from = (
            self.valid_from
            if self.valid_from.tzinfo
            else self.valid_from.replace(tzinfo=UTC)
        )
        valid_until = (
            self.valid_until
            if self.valid_until is None or self.valid_until.tzinfo
            else self.valid_until.replace(tzinfo=UTC)
        )
        if valid_until is not None and valid_until <= valid_from:
            raise ValueError("trust-root valid_until must be after valid_from")
        revocation_fields = (
            self.revoked_at,
            self.revoked_by,
            self.revoked_under_policy,
            self.revocation_reason,
            self.revocation_mode,
        )
        if self.status == "active" and any(item is not None for item in revocation_fields):
            raise ValueError("active trust roots cannot contain revocation metadata")
        if self.status == "revoked" and any(item is None for item in revocation_fields):
            raise ValueError("revoked trust roots require complete revocation metadata")
        return self

    def accepts_new_attestations(self, at: datetime | None = None) -> bool:
        moment = at or datetime.now(UTC)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        valid_from = (
            self.valid_from
            if self.valid_from.tzinfo
            else self.valid_from.replace(tzinfo=UTC)
        )
        valid_until = (
            self.valid_until
            if self.valid_until is None or self.valid_until.tzinfo
            else self.valid_until.replace(tzinfo=UTC)
        )
        return (
            self.status == "active"
            and valid_from <= moment
            and (valid_until is None or valid_until >= moment)
        )


class StructuralClaim(BaseModel):
    id: str
    title: str
    type: Literal["forbidden_import"] = "forbidden_import"
    forbidden_modules: list[str]
    severity: Literal["critical", "warning"] = "critical"
    rationale: str = ""
    scope: str = ""
    status: Literal[
        "proposed", "validated", "contested", "stale", "waived", "refuted", "superseded"
    ] = "validated"
    introduced_version: int = Field(default=1, ge=1)
    superseded_version: int | None = Field(default=None, ge=1)
    artifact_anchors: list[ArtifactAnchor] = Field(default_factory=list)
    evidence_obligations: list[EvidenceObligation] = Field(default_factory=list)
    authority: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_evidence_obligations(cls, value):
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        claim_id = str(normalized.get("id", "")).strip()
        obligations = []
        for raw in normalized.get("evidence_obligations") or []:
            if isinstance(raw, str):
                item = {"label": raw}
            elif isinstance(raw, EvidenceObligation):
                item = raw.model_dump()
            else:
                item = dict(raw)
            label = " ".join(str(item.get("label", "")).split())
            item_claim_id = str(item.get("claim_id") or claim_id).strip()
            if item_claim_id != claim_id:
                raise ValueError("evidence obligation claim_id must match its structural claim")
            item.update(
                {
                    "id": item.get("id") or stable_obligation_id(claim_id, label),
                    "claim_id": claim_id,
                    "label": label,
                }
            )
            obligations.append(item)
        normalized["evidence_obligations"] = obligations
        return normalized


class PythonImportSubstitution(BaseModel):
    kind: Literal["python_import_substitution"] = "python_import_substitution"
    path: str = Field(min_length=1, max_length=1000)
    from_module: str = Field(min_length=1, max_length=500)
    to_module: str = Field(min_length=1, max_length=500)

    @field_validator("path")
    @classmethod
    def require_safe_python_path(cls, value: str) -> str:
        normalized = value.strip()
        if (
            not normalized.endswith(".py")
            or normalized.startswith("/")
            or ".." in normalized.split("/")
        ):
            raise ValueError("import substitution path must be a safe repository-relative Python file")
        return normalized

    @field_validator("from_module", "to_module")
    @classmethod
    def require_module_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or any(not part.isidentifier() for part in normalized.split(".")):
            raise ValueError("import substitution modules must be dotted Python identifiers")
        return normalized

    @model_validator(mode="after")
    def require_change(self):
        if self.from_module == self.to_module:
            raise ValueError("import substitution must change the module")
        return self


class InterpretationCandidate(BaseModel):
    id: str = Field(default_factory=lambda: new_id("candidate"))
    title: str = Field(min_length=1, max_length=240)
    summary: str = Field(min_length=1, max_length=2000)
    structural_delta: PythonImportSubstitution
    uncertainties: list[str] = Field(default_factory=list, max_length=20)
    provenance: str = Field(min_length=1, max_length=1000)
    confidence: float | None = Field(default=None, ge=0, le=1)
    status: Literal["active", "eliminated", "selected", "not_selected", "realized"] = "active"

    @field_validator("title", "summary", "provenance")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("candidate text fields must not be blank")
        return normalized

    @field_validator("uncertainties")
    @classmethod
    def normalize_uncertainties(cls, value: list[str]) -> list[str]:
        normalized = [" ".join(item.split()) for item in value if item.strip()]
        return list(dict.fromkeys(normalized))


class ClarificationRecord(BaseModel):
    id: str = Field(default_factory=lambda: new_id("clarification"))
    intent_revision: int = Field(ge=2)
    question: str = Field(min_length=1, max_length=2000)
    answer: str = Field(min_length=1, max_length=4000)
    actor: str = Field(min_length=1, max_length=200)
    before_candidate_ids: list[str] = Field(min_length=1, max_length=20)
    after_candidate_ids: list[str] = Field(min_length=1, max_length=20)
    eliminated_candidate_ids: list[str] = Field(default_factory=list, max_length=20)
    revised_candidate_ids: list[str] = Field(default_factory=list, max_length=20)
    added_candidate_ids: list[str] = Field(default_factory=list, max_length=20)
    resolved_uncertainties: dict[str, list[str]] = Field(default_factory=dict)
    before_candidates: list[InterpretationCandidate] = Field(min_length=1, max_length=20)
    after_candidates: list[InterpretationCandidate] = Field(min_length=1, max_length=20)
    provenance: str = Field(default="human_clarification", min_length=1, max_length=500)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RehydratedDeltaCandidate(BaseModel):
    id: str = Field(default_factory=lambda: new_id("rehydrated"))
    structural_delta: PythonImportSubstitution
    confidence: float = Field(ge=0, le=1)
    provenance: str = Field(default="psi/python-ast-diff-v1", min_length=1, max_length=500)
    evidence: list[str] = Field(default_factory=list, max_length=20)


class RealizationRecord(BaseModel):
    id: str = Field(default_factory=lambda: new_id("realization"))
    operator: Literal["phi/python-import-substitution-v1"] = (
        "phi/python-import-substitution-v1"
    )
    status: Literal["failed", "succeeded"]
    intent_id: str
    candidate_id: str
    base_ref: str
    target_ref: str | None = None
    git_ref: str | None = None
    predicted_delta: PythonImportSubstitution
    artifact_diff: str = ""
    failed_preconditions: list[str] = Field(default_factory=list, max_length=20)
    rehydrated_candidates: list[RehydratedDeltaCandidate] = Field(default_factory=list, max_length=20)
    selected_rehydration_id: str | None = None
    unobservable_relations: list[str] = Field(default_factory=list, max_length=20)
    round_trip_discrepancy: float | None = Field(default=None, ge=0, le=1)
    observable_coverage: float = Field(default=0, ge=0, le=1)
    actor: str = Field(min_length=1, max_length=200)
    provenance: str = Field(default="intent-selection/phi/psi", min_length=1, max_length=500)
    review_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class IntentMap(BaseModel):
    id: str = Field(default_factory=lambda: new_id("intent"))
    project_id: str
    request: str = Field(min_length=1, max_length=8000)
    context: str = Field(min_length=1, max_length=8000)
    base_ref: str
    base_version: int = Field(ge=1)
    revision: int = Field(default=1, ge=1)
    created_by: str = Field(min_length=1, max_length=200)
    candidates: list[InterpretationCandidate] = Field(min_length=2, max_length=20)
    clarification_history: list[ClarificationRecord] = Field(default_factory=list, max_length=100)
    status: Literal[
        "clarification_required", "ready_for_selection", "selected", "realized"
    ] = "clarification_required"
    selected_candidate_id: str | None = None
    selection_actor: str | None = None
    selection_reason: str | None = None
    selected_at: datetime | None = None
    realized_review_id: str | None = None
    realization_attempts: list[RealizationRecord] = Field(default_factory=list, max_length=50)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_candidate_identity(self):
        candidate_ids = [candidate.id for candidate in self.candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("intent candidate IDs must be unique")
        if self.selected_candidate_id and self.selected_candidate_id not in candidate_ids:
            raise ValueError("selected candidate must belong to the intent")
        return self


class Evidence(BaseModel):
    id: str = Field(default_factory=lambda: new_id("evidence"))
    kind: Literal["static_analysis", "tests", "policy", "git", "attestation"]
    status: Literal["pass", "fail", "unknown", "not_run"]
    outcome: Literal["supports", "contests", "inconclusive", "not_applicable"] = "supports"
    summary: str
    claim_ids: list[str] = Field(default_factory=list)
    obligation_ids: list[str] = Field(default_factory=list)
    artifact_ref: str | None = None
    provenance: str = ""
    recorded_by: str = ""
    authority: str = ""
    policy_id: str = ""
    freshness: Literal["current", "stale", "unknown"] = "current"
    invalidated_reason: str | None = None
    details: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="before")
    @classmethod
    def infer_legacy_outcome(cls, value):
        if isinstance(value, dict) and "outcome" not in value:
            value = dict(value)
            value["outcome"] = {
                "pass": "supports",
                "fail": "contests",
                "unknown": "inconclusive",
                "not_run": "inconclusive",
            }.get(value.get("status"), "inconclusive")
        return value


class ClaimDelta(BaseModel):
    claim_id: str
    operation: Literal["add", "modify", "contest", "supersede"] = "contest"
    status: Literal["proposed", "contested", "unobservable", "accepted", "rejected"] = "proposed"
    summary: str
    affected_scope: str = ""
    before: str | None = None
    after: str | None = None
    artifact_anchors: list[ArtifactAnchor] = Field(default_factory=list)
    source: Literal["proposed", "rehydrated"] = "rehydrated"
    confidence: float | None = Field(default=None, ge=0, le=1)


class Finding(BaseModel):
    id: str = Field(default_factory=lambda: new_id("finding"))
    rule_id: str
    kind: Literal[
        "forbidden_dependency",
        "unobservable",
        "syntax_error",
        "test_failure",
        "stale_base",
        "overlap",
    ]
    severity: Literal["critical", "warning", "info"]
    message: str
    path: str | None = None
    line: int | None = None
    status: Literal["open", "waived", "resolved"] = "open"
    details: dict = Field(default_factory=dict)


class Waiver(BaseModel):
    id: str = Field(default_factory=lambda: new_id("waiver"))
    finding_ids: list[str] = Field(default_factory=list)
    obligation_ids: list[str] = Field(default_factory=list)
    actor: str
    reason: str
    scope: str
    expires_at: datetime
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AuthorityGrant(BaseModel):
    authority: str = Field(min_length=1, max_length=160)
    actors: list[str] = Field(min_length=1, max_length=100)
    actions: list[GovernedAction] = Field(
        default_factory=lambda: ["commit", "waive", "rebase", "reject", "rollback", "attest"]
    )


class DecisionRecord(BaseModel):
    id: str = Field(default_factory=lambda: new_id("decision"))
    action: DecisionKind
    actor: str
    authority: str
    policy_id: str
    reason: str | None = None
    waiver_ids: list[str] = Field(default_factory=list)
    provenance: Literal["project_authority_grant", "local_single_user_policy"]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ProjectCommitment(BaseModel):
    """A human-authored project commitment, not an inferred or verified fact."""

    id: str = Field(default_factory=lambda: new_id("commitment"), min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=240)
    statement: str = Field(min_length=1, max_length=4000)
    category: Literal["behavior", "interface", "dependency", "authority", "compatibility"] = "behavior"
    paths: list[str] = Field(min_length=1, max_length=100)
    verification: str = Field(min_length=8, max_length=2000)

    @field_validator("title", "statement", "verification")
    @classmethod
    def meaningful_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("commitment fields cannot be blank")
        return value.strip()

    @field_validator("paths")
    @classmethod
    def repository_paths(cls, paths: list[str]) -> list[str]:
        for path in paths:
            if not path or path.startswith("/") or "\\" in path or any(part in {"", ".", ".."} for part in path.split("/")):
                raise ValueError("commitment paths must be repository-relative files")
        return list(dict.fromkeys(paths))


class SourceReadingDraft(BaseModel):
    """An author's interpretation of a bounded source span; never test evidence."""
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1, max_length=1000)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    label: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=300)
    relation: Literal["supports", "tension", "context"] = "context"

    @field_validator("label", "summary")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source reading text cannot be blank")
        return value.strip()

    @model_validator(mode="after")
    def bounded_lines(self):
        if not self.start_line <= self.end_line < self.start_line + 12:
            raise ValueError("select 1 to 12 consecutive source lines")
        return self


class SourceReading(SourceReadingDraft):
    excerpt: str
    version_ref: str


class CommitmentChange(BaseModel):
    before: ProjectCommitment | None = None
    after: ProjectCommitment
    request: str = Field(min_length=1, max_length=8000)
    reason: str = Field(min_length=8, max_length=4000)
    obligation_id: str
    recorded_by: str
    source_readings: list[SourceReading] = Field(default_factory=list, max_length=12)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ReviewPackage(BaseModel):
    id: str = Field(default_factory=lambda: new_id("review"))
    project_id: str
    base_ref: str
    target_ref: str
    base_version: int
    current_project_version: int
    revision: int = Field(default=1, ge=1)
    status: Literal[
        "open", "committed", "rebase_required", "rejected", "rolled_back"
    ] = "open"
    summary: str = ""
    intent_summary: str = ""
    intent_id: str | None = None
    selected_interpretation_id: str | None = None
    realization_id: str | None = None
    proposer: str = "coding-agent"
    predecessor_review_id: str | None = None
    predecessor_revision: int | None = None
    revision_context: dict = Field(default_factory=dict)
    external_url: str | None = Field(default=None, max_length=1000)
    external_label: str | None = Field(default=None, max_length=200)
    patch_summary: str = ""
    changed_paths: list[str] = Field(default_factory=list)
    claim_deltas: list[ClaimDelta] = Field(default_factory=list)
    commitment_baseline: list[ProjectCommitment] = Field(default_factory=list)
    commitment_changes: list[CommitmentChange] = Field(default_factory=list, max_length=100)
    rehydrated_deltas: list[RehydratedDeltaCandidate] = Field(default_factory=list)
    round_trip_discrepancy: float | None = Field(default=None, ge=0)
    observable_coverage: float | None = Field(default=None, ge=0, le=1)
    evidence_obligations: list[EvidenceObligation] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    waivers: list[Waiver] = Field(default_factory=list)
    governing_policy: str = "local-single-user/v1"
    required_authorities: list[str] = Field(default_factory=lambda: ["local operator"])
    decision_records: list[DecisionRecord] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DecisionAction(BaseModel):
    action: DecisionKind
    actor: str
    authority: str | None = None
    policy_id: str | None = None
    reason: str | None = None
    scope: str | None = None
    expires_at: datetime | None = None
    finding_ids: list[str] = Field(default_factory=list)
    obligation_ids: list[str] = Field(default_factory=list)


class AuditEvent(BaseModel):
    id: str = Field(default_factory=lambda: new_id("event"))
    review_id: str
    action: str
    actor: str
    reason: str | None = None
    payload: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ProjectAuditEvent(BaseModel):
    id: str = Field(default_factory=lambda: new_id("project-event"))
    project_id: str
    project_version: int = Field(ge=1)
    action: str
    actor: str
    authority: str
    policy_id: str
    reason: str
    payload: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TransitionResult(BaseModel):
    review: ReviewPackage
    event: AuditEvent
    new_project_version: int | None = None


class AdmissionCheck(BaseModel):
    key: str
    label: str
    status: Literal["pass", "block", "warn"]
    summary: str


class EvidenceObligationStatus(BaseModel):
    obligation_id: str
    claim_id: str
    label: str
    status: Literal["satisfied", "waived", "missing", "contested", "stale"]
    evidence_ids: list[str] = Field(default_factory=list)
    waiver_ids: list[str] = Field(default_factory=list)


class ChangePackageManifest(BaseModel):
    package_id: str
    project_name: str
    repo_label: str
    intent_summary: str
    proposer: str
    notation: dict[str, int]
    admission_checks: list[AdmissionCheck]
    obligation_statuses: list[EvidenceObligationStatus] = Field(default_factory=list)
    invalidated_evidence_ids: list[str] = Field(default_factory=list)
    gate_state: Literal[
        "blocked", "ready", "committed", "rebase_required", "rejected", "rolled_back"
    ]
    committable: bool
    blockers: list[str] = Field(default_factory=list)
    authority_actions: list[str] = Field(default_factory=list)
    governing_policy: str
    required_authorities: list[str] = Field(default_factory=list)
    decision_recorded: bool = False


class ContractGraphNode(BaseModel):
    id: str
    type: Literal[
        "base_state",
        "proposal",
        "current_state",
        "claim",
        "artifact",
        "evidence",
        "finding",
        "authority",
        "decision",
        "intent",
        "interpretation",
        "realization",
        "rehydration",
    ]
    label: str
    status: str
    summary: str = ""
    metadata: dict = Field(default_factory=dict)


class ContractGraphEdge(BaseModel):
    id: str
    source: str
    target: str
    relation: Literal[
        "proposes",
        "selects",
        "changes",
        "observes",
        "realizes",
        "rehydrates",
        "round_trip_matches",
        "round_trip_diverges",
        "validates",
        "supports",
        "contests",
        "inconclusive",
        "authorizes",
        "commits",
        "waives",
        "rejects",
        "requires_rebase",
        "rolls_back",
        "governs",
    ]
    label: str


class ContractGraph(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    format: Literal["agentic-consensus/contract-graph@0.1"] = Field(
        default="agentic-consensus/contract-graph@0.1",
        validation_alias="schema",
        serialization_alias="schema",
    )
    project_id: str
    review_id: str
    project_version: int = Field(ge=1)
    review_status: Literal[
        "open", "committed", "rebase_required", "rejected", "rolled_back"
    ]
    nodes: list[ContractGraphNode]
    edges: list[ContractGraphEdge]


class RepositorySource(BaseModel):
    """Reviewer-safe provenance for a repository imported from an external provider."""

    provider: Literal["github"] = "github"
    repository_id: int = Field(gt=0)
    installation_id: int = Field(gt=0)
    full_name: str = Field(min_length=3, max_length=300)
    html_url: str = Field(min_length=10, max_length=1000)
    default_branch: str = Field(min_length=1, max_length=255)
    visibility: Literal["public", "private", "internal"]
    connected_by: str = Field(min_length=1, max_length=200)
    imported_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Project(BaseModel):
    id: str = Field(default_factory=lambda: new_id("project"))
    name: str
    repo_path: str
    repo_label: str | None = None
    source: RepositorySource | None = None
    version: int = 1
    head_ref: str
    test_command: list[str] = Field(default_factory=list)
    claims: list[StructuralClaim] = Field(default_factory=list)
    commitments: list[ProjectCommitment] = Field(default_factory=list, max_length=100)
    policy_id: str = Field(default="local-single-user/v1", min_length=1, max_length=200)
    default_authority: str = Field(default="local operator", min_length=1, max_length=160)
    authority_grants: list[AuthorityGrant] = Field(default_factory=list, max_length=100)
    attestation_trust_roots: list[AttestationTrustRoot] = Field(default_factory=list, max_length=100)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def unique_attestation_roots(self):
        key_ids = [item.key_id for item in self.attestation_trust_roots]
        if len(key_ids) != len(set(key_ids)):
            raise ValueError("attestation trust-root key IDs must be unique")
        public_keys = [item.public_key_base64 for item in self.attestation_trust_roots]
        if len(public_keys) != len(set(public_keys)):
            raise ValueError("attestation trust-root public keys must be unique")
        return self
