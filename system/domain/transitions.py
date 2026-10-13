from __future__ import annotations

from datetime import UTC, datetime

from system.domain.models import (
    AttestationTrustRoot,
    AuditEvent,
    DecisionAction,
    EvidenceObligationStatus,
    ReviewPackage,
    TransitionResult,
    Waiver,
)


class DecisionBlocked(ValueError):
    """A requested human action violates the explicit transition policy."""


def _waiver_is_active(waiver: Waiver, now: datetime) -> bool:
    expires_at = (
        waiver.expires_at
        if waiver.expires_at.tzinfo
        else waiver.expires_at.replace(tzinfo=UTC)
    )
    return expires_at > now


def effectively_open_findings(review: ReviewPackage) -> list:
    now = datetime.now(UTC)
    active_finding_ids = {
        finding_id
        for waiver in review.waivers
        if _waiver_is_active(waiver, now)
        for finding_id in waiver.finding_ids
    }
    return [
        finding
        for finding in review.findings
        if (
            finding.status == "open"
            or (finding.status == "waived" and finding.id not in active_finding_ids)
        )
    ]


def open_critical_findings(review: ReviewPackage) -> list:
    return [
        finding for finding in effectively_open_findings(review) if finding.severity == "critical"
    ]


def evidence_obligation_statuses(
    review: ReviewPackage,
    trust_roots: list[AttestationTrustRoot] | None = None,
) -> list[EvidenceObligationStatus]:
    statuses: list[EvidenceObligationStatus] = []
    now = datetime.now(UTC)
    retroactively_revoked_keys = {
        root.key_id
        for root in trust_roots or []
        if root.status == "revoked" and root.revocation_mode == "retroactive"
    }
    for obligation in review.evidence_obligations:
        linked = [item for item in review.evidence if obligation.id in item.obligation_ids]
        invalidated = [
            item
            for item in linked
            if item.details.get("key_id") in retroactively_revoked_keys
        ]
        invalidated_ids = {item.id for item in invalidated}
        active_waivers = [
            item
            for item in review.waivers
            if obligation.id in item.obligation_ids
            and _waiver_is_active(item, now)
        ]
        satisfied = [
            item
            for item in linked
            if item.kind == obligation.evidence_kind
            and item.id not in invalidated_ids
            and (
                obligation.verification == "authorized_record"
                or (
                    item.details.get("signature_verified") is True
                    and item.details.get("signature_algorithm") == "ed25519"
                    and item.details.get("verifier_id") == obligation.required_verifier_id
                    and obligation.required_verified_level
                    in item.details.get("verified_levels", [])
                )
            )
            and (
                not obligation.required_provenance_prefix
                or item.provenance.startswith(obligation.required_provenance_prefix)
            )
            and item.status == "pass"
            and item.outcome == "supports"
            and item.freshness == "current"
            and item.artifact_ref == review.target_ref
        ]
        if satisfied:
            status = "satisfied"
            evidence_ids = [item.id for item in satisfied]
        elif active_waivers:
            status = "waived"
            evidence_ids = [item.id for item in linked]
        elif invalidated or any(
            item.freshness == "stale" or item.artifact_ref != review.target_ref
            for item in linked
        ):
            status = "stale"
            evidence_ids = [item.id for item in linked]
        elif any(item.status == "fail" or item.outcome == "contests" for item in linked):
            status = "contested"
            evidence_ids = [item.id for item in linked]
        else:
            status = "missing"
            evidence_ids = [item.id for item in linked]
        statuses.append(
            EvidenceObligationStatus(
                obligation_id=obligation.id,
                claim_id=obligation.claim_id,
                label=obligation.label,
                status=status,
                evidence_ids=evidence_ids,
                waiver_ids=[item.id for item in active_waivers],
            )
        )
    return statuses


def _require_actor(action: DecisionAction) -> None:
    if not action.actor.strip():
        raise DecisionBlocked("an identified human actor is required")


def _require_reason(action: DecisionAction) -> None:
    if not action.reason or len(action.reason.strip()) < 8:
        raise DecisionBlocked("a substantive reason is required")


def _commit(review: ReviewPackage, action: DecisionAction) -> TransitionResult:
    if review.status != "open":
        raise DecisionBlocked(f"cannot commit a review in {review.status} status")
    if review.base_version != review.current_project_version:
        raise DecisionBlocked("stale base: rebase the proposal before commit")

    evidence_by_kind = {item.kind: item for item in review.evidence}
    for required in ("static_analysis", "tests"):
        evidence = evidence_by_kind.get(required)
        if evidence is None or evidence.status != "pass":
            raise DecisionBlocked(f"passing {required.replace('_', ' ')} evidence is required")
    failed = [item.kind for item in review.evidence if item.status == "fail"]
    if failed:
        raise DecisionBlocked(f"failed evidence blocks commit: {', '.join(failed)}")

    critical = open_critical_findings(review)
    if critical:
        noun = "finding" if len(critical) == 1 else "findings"
        verb = "blocks" if len(critical) == 1 else "block"
        raise DecisionBlocked(f"{len(critical)} open critical {noun} {verb} commit")

    unsatisfied = [
        item
        for item in evidence_obligation_statuses(review)
        if item.status not in {"satisfied", "waived"}
    ]
    if unsatisfied:
        count = len(unsatisfied)
        noun = "evidence obligation" if count == 1 else "evidence obligations"
        raise DecisionBlocked(f"{count} unsatisfied {noun} block commit")

    next_review = review.model_copy(deep=True)
    next_review.status = "committed"
    next_review.updated_at = datetime.now(UTC)
    next_version = review.current_project_version + 1
    next_review.current_project_version = next_version
    return TransitionResult(
        review=next_review,
        event=AuditEvent(review_id=review.id, action="commit", actor=action.actor, reason=action.reason),
        new_project_version=next_version,
    )


def _waive(review: ReviewPackage, action: DecisionAction) -> TransitionResult:
    if review.status != "open":
        raise DecisionBlocked(f"cannot waive a review in {review.status} status")
    _require_reason(action)
    if not action.scope or not action.scope.strip():
        raise DecisionBlocked("waiver scope is required")
    if action.expires_at is None:
        raise DecisionBlocked("waiver expiry is required")
    expires_at = action.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        raise DecisionBlocked("waiver expiry must be in the future")
    if not action.finding_ids and not action.obligation_ids:
        raise DecisionBlocked("at least one finding or evidence obligation must be selected for waiver")

    next_review = review.model_copy(deep=True)
    selected_findings = set(action.finding_ids)
    effectively_open_ids = {item.id for item in effectively_open_findings(review)}
    matched = [
        finding
        for finding in next_review.findings
        if finding.id in selected_findings and finding.id in effectively_open_ids
    ]
    if len(matched) != len(selected_findings):
        raise DecisionBlocked("waiver contains an unknown or closed finding")
    for finding in matched:
        finding.status = "waived"
    selected_obligations = set(action.obligation_ids)
    obligation_by_id = {item.id: item for item in next_review.evidence_obligations}
    if any(item not in obligation_by_id for item in selected_obligations):
        raise DecisionBlocked("waiver contains an unknown evidence obligation")
    nonwaivable = [
        obligation_by_id[item].label
        for item in selected_obligations
        if not obligation_by_id[item].waivable
    ]
    if nonwaivable:
        raise DecisionBlocked(f"evidence obligation is not waivable: {nonwaivable[0]}")
    waiver = Waiver(
        finding_ids=action.finding_ids,
        obligation_ids=action.obligation_ids,
        actor=action.actor,
        reason=action.reason or "",
        scope=action.scope,
        expires_at=expires_at,
    )
    next_review.waivers.append(waiver)
    next_review.updated_at = datetime.now(UTC)
    return TransitionResult(
        review=next_review,
        event=AuditEvent(
            review_id=review.id,
            action="waive",
            actor=action.actor,
            reason=action.reason,
            payload={
                "waiver_id": waiver.id,
                "finding_ids": action.finding_ids,
                "obligation_ids": action.obligation_ids,
                "scope": action.scope,
            },
        ),
    )


def _simple_transition(review: ReviewPackage, action: DecisionAction) -> TransitionResult:
    if review.status != "open":
        raise DecisionBlocked(f"cannot {action.action} a review in {review.status} status")
    if action.action in {"reject", "rebase"}:
        _require_reason(action)
    next_review = review.model_copy(deep=True)
    next_review.status = "rebase_required" if action.action == "rebase" else "rejected"
    next_review.updated_at = datetime.now(UTC)
    return TransitionResult(
        review=next_review,
        event=AuditEvent(review_id=review.id, action=action.action, actor=action.actor, reason=action.reason),
    )


def _rollback(review: ReviewPackage, action: DecisionAction) -> TransitionResult:
    if review.status != "committed":
        raise DecisionBlocked("only a committed review can be rolled back")
    _require_reason(action)
    next_review = review.model_copy(deep=True)
    next_review.status = "rolled_back"
    next_review.updated_at = datetime.now(UTC)
    return TransitionResult(
        review=next_review,
        event=AuditEvent(review_id=review.id, action="rollback", actor=action.actor, reason=action.reason),
        new_project_version=review.current_project_version + 1,
    )


def decide(review: ReviewPackage, action: DecisionAction) -> TransitionResult:
    _require_actor(action)
    if action.action == "commit":
        return _commit(review, action)
    if action.action == "waive":
        return _waive(review, action)
    if action.action in {"rebase", "reject"}:
        return _simple_transition(review, action)
    if action.action == "rollback":
        return _rollback(review, action)
    raise DecisionBlocked(f"unsupported action: {action.action}")
