"""Manual project-state correspondence using the existing evidence/decision contract."""
from datetime import UTC, datetime

from system.domain.models import (
    ArtifactAnchor, AuditEvent, ClaimDelta, CommitmentChange, EvidenceObligation,
    ProjectCommitment, SourceReading, SourceReadingDraft, stable_obligation_id,
)
from system.domain.transitions import DecisionBlocked
from system.services.git_service import GitError, GitRepository


def obligation(commitment):
    return EvidenceObligation(id=stable_obligation_id(commitment.id, "commitment-verification"),
        claim_id=commitment.id, label=commitment.verification)


def bind_baseline(review, project):
    review.commitment_baseline = [item.model_copy(deep=True) for item in project.commitments]
    for item in review.commitment_baseline:
        if set(item.paths) & set(review.changed_paths):
            review.evidence_obligations.append(obligation(item))


def propose(review, project, *, commitment_id, actor, request, reason, expected_revision, source_readings=None, **values):
    if review.status != "open":
        raise DecisionBlocked("only an open review can receive a commitment proposal")
    if review.revision != expected_revision:
        raise DecisionBlocked("the review changed; reload before saving your proposal")
    if review.base_version != project.version:
        raise DecisionBlocked("the project baseline changed; analyze a new review before proposing")
    previous = next((c for c in review.commitment_changes if c.after.id == commitment_id), None)
    baseline = next((c for c in review.commitment_baseline if c.id == commitment_id), None)
    if commitment_id and not previous and not baseline:
        raise DecisionBlocked("unknown commitment in this review baseline")
    if not actor.strip() or not request.strip() or len(reason.strip()) < 8:
        raise ValueError("an actor, original request and substantive rationale are required")
    after = ProjectCommitment(**values, **({"id": commitment_id} if commitment_id else {}))
    allowed_paths = set(review.changed_paths) | set(baseline.paths if baseline else []) | set(previous.after.paths if previous else [])
    if not set(after.paths) <= allowed_paths:
        raise ValueError("link changed files or files already anchored by the baseline commitment")
    notes = list(previous.source_readings) if previous and source_readings is None else []
    if source_readings is not None:
        repository = GitRepository(project.repo_path)
        for value in source_readings:
            draft = SourceReadingDraft.model_validate(value)
            if draft.path not in after.paths:
                raise ValueError("source readings must reference files linked to this commitment")
            try:
                file = repository.snapshot_file(review.target_ref, draft.path)
            except (GitError, FileNotFoundError, ValueError) as exc:
                raise ValueError("the source reading is unavailable in the review target") from exc
            lines = (file.get("content") or "").splitlines()
            if file["status"] != "text" or draft.end_line > len(lines):
                raise ValueError("source reading lines must exist in a readable target file")
            notes.append(SourceReading(**draft.model_dump(), version_ref=review.target_ref,
                excerpt="\n".join(lines[draft.start_line - 1:draft.end_line])))
    if any(note.path not in after.paths for note in notes):
        raise ValueError("remove source readings before unlinking their files")
    if previous and previous.after == after and previous.request == request.strip() and previous.reason == reason.strip() and previous.source_readings == notes:
        raise ValueError("the proposal has no changes to save")
    if not previous and len(review.commitment_changes) >= 100:
        raise ValueError("this review already has 100 commitment proposals")
    if not baseline and not previous and len(project.commitments) + sum(c.before is None for c in review.commitment_changes) >= 100:
        raise ValueError("this project already has 100 commitments including proposed additions")
    required = obligation(after)
    # A revised meaning requires a new obligation identity; an earlier waiver or
    # attestation must never silently transfer to the replacement proposal.
    required.id = stable_obligation_id(after.id, f"commitment-verification/revision-{review.revision + 1}")
    replaced_ids = {o.id for o in review.evidence_obligations if o.claim_id == after.id}
    change = CommitmentChange(before=baseline, after=after, request=request.strip(), reason=reason.strip(),
        obligation_id=required.id, recorded_by=actor.strip(), source_readings=notes)
    updated = review.model_copy(deep=True)
    updated.commitment_changes = [c for c in updated.commitment_changes if c.after.id != after.id] + [change]
    updated.evidence_obligations = [o for o in updated.evidence_obligations if o.id not in replaced_ids] + [required]
    for evidence in updated.evidence:
        if replaced_ids & set(evidence.obligation_ids):
            evidence.freshness = "stale"
            evidence.invalidated_reason = "The commitment proposal changed after this verification was recorded"
    updated.claim_deltas = [d for d in updated.claim_deltas if d.claim_id != after.id] + [ClaimDelta(
        claim_id=after.id, operation="modify" if baseline else "add", status="proposed", summary=after.title,
        before=baseline.statement if baseline else None, after=after.statement, source="proposed",
        artifact_anchors=[ArtifactAnchor(path=p, version_ref=review.target_ref) for p in after.paths])]
    updated.revision += 1
    updated.updated_at = datetime.now(UTC)
    event = AuditEvent(review_id=review.id, action="revise_commitment" if previous else "propose_commitment", actor=actor.strip(),
        reason=reason.strip(), payload={"commitment_id": after.id, "target_ref": review.target_ref,
        "before": previous.model_dump(mode="json") if previous else None,
        "after": after.model_dump(mode="json"), "request": change.request,
        "proposal": change.model_dump(mode="json")})
    return updated, event


def apply_decision(project, review, action):
    """Called only after existing authority and evidence gates, before atomic persistence."""
    if action not in {"commit", "rollback"}:
        return
    indexed = {item.id: item for item in project.commitments}
    for change in review.commitment_changes:
        current = indexed.get(change.after.id)
        if action == "commit":
            if current != change.before:
                raise DecisionBlocked("commitment baseline changed; rebase the proposal")
            indexed[change.after.id] = change.after.model_copy(deep=True)
        else:
            if current != change.after:
                raise DecisionBlocked("a later decision changed this commitment; reconcile it before rollback")
            if change.before is None:
                indexed.pop(change.after.id, None)
            else:
                indexed[change.after.id] = change.before.model_copy(deep=True)
    project.commitments = list(indexed.values())
