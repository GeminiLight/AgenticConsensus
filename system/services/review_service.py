from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from system.domain.models import (
    AdmissionCheck,
    ArtifactAnchor,
    AttestationTrustRoot,
    AuditEvent,
    ChangePackageManifest,
    ClaimDelta,
    ContractGraph,
    ContractGraphEdge,
    ContractGraphNode,
    ClarificationRecord,
    DecisionAction,
    DecisionRecord,
    Evidence,
    Finding,
    IntentMap,
    InterpretationCandidate,
    PythonImportSubstitution,
    Project,
    ProjectAuditEvent,
    RepositorySource,
    RealizationRecord,
    RehydratedDeltaCandidate,
    ReviewPackage,
    StructuralClaim,
    new_id,
)
from system.services.attestation import (
    TRUST_ROOT_POSSESSION_LEVEL,
    TRUST_ROOT_POSSESSION_POLICY_URI,
    AttestationVerificationError,
    build_trust_root_possession_template as build_possession_template,
    verify_dsse_vsa,
)
from system.domain.transitions import (
    DecisionBlocked,
    decide,
    evidence_obligation_statuses,
    open_critical_findings,
)
from system.services.analyzer import analyze_python_imports, rehydrate_python_import_substitutions
from system.services.database import (
    ConcurrentTransitionError,
    Database,
    DuplicateReviewRecordError,
)
from system.services.git_service import GitRepository
from system.services.test_runner import run_tests
from system.services import commitments


class DuplicateProjectError(ValueError):
    pass


class DuplicateReviewError(ValueError):
    pass


def _count_phrase(count: int, singular: str, plural: str | None = None) -> str:
    return f"{count} {singular if count == 1 else (plural or singular + 's')}"


def _test_clause(status: str) -> str:
    return {
        "pass": "tests passed",
        "fail": "tests failed",
        "unknown": "the test outcome is unknown",
        "not_run": "tests were not run",
        "missing": "test evidence is missing",
    }.get(status, f"the test outcome is {status}")


def _revocation_valid_until(
    root: AttestationTrustRoot, revoked_at: datetime
) -> datetime | None:
    """Close an active validity window without inventing one for a scheduled key."""
    valid_from = root.valid_from if root.valid_from.tzinfo else root.valid_from.replace(tzinfo=UTC)
    return revoked_at if revoked_at > valid_from else root.valid_until


class ReviewService:
    def __init__(self, database: Database):
        self.database = database

    def create_project(
        self,
        *,
        name: str,
        repo_path: str | Path,
        head_ref: str,
        test_command: list[str],
        claims: list[StructuralClaim],
        repo_label: str | None = None,
        policy_id: str = "local-single-user/v1",
        default_authority: str = "local operator",
        authority_grants: list | None = None,
        attestation_trust_roots: list | None = None,
        source: RepositorySource | None = None,
    ) -> Project:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("project name cannot be empty")
        repository = GitRepository(repo_path)
        existing = self.database.find_project_by_repo(repository.path)
        if existing is not None:
            raise DuplicateProjectError(f"repository is already registered as project {existing.id}")
        resolved_head = repository.resolve(head_ref)
        project = Project(
            name=normalized_name,
            repo_path=str(repository.path),
            repo_label=repo_label.strip() if repo_label and repo_label.strip() else None,
            source=source,
            head_ref=resolved_head,
            test_command=test_command,
            claims=claims,
            policy_id=policy_id.strip(),
            default_authority=default_authority.strip(),
            authority_grants=authority_grants or [],
            attestation_trust_roots=attestation_trust_roots or [],
        )
        self.database.save_project(project)
        return project

    def propose_commitment(self, review_id: str, **payload) -> ReviewPackage:
        review = self.database.get_review(review_id)
        project = self.database.get_project(review.project_id)
        updated, event = commitments.propose(review, project, **payload)
        try:
            self.database.apply_transition(project=project, review=updated, event=event,
                expected_project_version=project.version, expected_review_revision=review.revision)
        except ConcurrentTransitionError as exc:
            raise DecisionBlocked(str(exc)) from exc
        return updated

    def draft_commitment(self, review_id: str, *, expected_revision: int, request: str = "", language: str = "en") -> dict:
        from system.services.commitment_drafts import draft_commitment
        review = self.database.get_review(review_id)
        if review.status != "open" or review.revision != expected_revision:
            raise DecisionBlocked("the review changed; reload before drafting")
        project = self.database.get_project(review.project_id)
        if project.version != review.base_version:
            raise DecisionBlocked("the project baseline changed; review the new baseline first")
        if not review.changed_paths:
            raise ValueError("No changed files are available to ground a draft.")
        return draft_commitment(review, project, request, language)

    def revise_review(self, review_id: str, *, target_ref: str, expected_revision: int, actor: str) -> ReviewPackage:
        from system.domain.models import stable_obligation_id
        previous = self.database.get_review(review_id)
        project = self.database.get_project(previous.project_id)
        if previous.status != "rebase_required" or previous.revision != expected_revision:
            raise DecisionBlocked("the previous review changed or does not require an update; reload it")
        if project.version != previous.base_version:
            raise DecisionBlocked("the project baseline advanced; reconcile its commitments in a new review")
        if GitRepository(project.repo_path).resolve(target_ref) == previous.target_ref:
            raise DecisionBlocked("choose a revised commit, not the previously reviewed target")
        review, event = self._build_review(project.id, base_ref=previous.base_ref, target_ref=target_ref,
            proposer=previous.proposer, intent_summary=previous.intent_summary,
            intent_id=previous.intent_id, selected_interpretation_id=previous.selected_interpretation_id,
            external_url=previous.external_url, external_label=previous.external_label)
        review.predecessor_review_id = previous.id
        review.predecessor_revision = previous.revision
        review.revision_context = {"target_ref": previous.target_ref,
            "reason": previous.decision_records[-1].reason if previous.decision_records else "",
            "findings": [f.model_dump(mode="json") for f in previous.findings if f.status == "open"],
            "source_readings": [n.model_dump(mode="json") for c in previous.commitment_changes for n in c.source_readings]}
        review.commitment_changes = [change.model_copy(deep=True) for change in previous.commitment_changes]
        # Copy requirements, never waivers, attestations, decisions or old line anchors.
        inherited_claims = {o.claim_id for o in previous.evidence_obligations}
        review.evidence_obligations = [o for o in review.evidence_obligations if o.claim_id not in inherited_claims]
        for old in previous.evidence_obligations:
            fresh = old.model_copy(deep=True)
            fresh.id = stable_obligation_id(old.claim_id, f"revision:{review.id}:{old.id}")
            review.evidence_obligations.append(fresh)
            for change in review.commitment_changes:
                if change.obligation_id == old.id:
                    change.obligation_id = fresh.id
                    change.source_readings = []
        ids = {c.after.id for c in review.commitment_changes}
        review.claim_deltas = [d for d in review.claim_deltas if d.claim_id not in ids]
        for old in previous.claim_deltas:
            if old.claim_id in ids:
                fresh = old.model_copy(deep=True)
                for anchor in fresh.artifact_anchors:
                    anchor.version_ref = review.target_ref
                review.claim_deltas.append(fresh)
        event.actor = actor
        event.payload.update(predecessor_review_id=previous.id, predecessor_revision=previous.revision,
            inherited_commitments=sorted(ids), previous_update_reason=review.revision_context["reason"])
        try:
            self.database.create_review(review, event)
        except DuplicateReviewRecordError as exc:
            raise DuplicateReviewError(str(exc)) from exc
        except ConcurrentTransitionError as exc:
            raise DecisionBlocked(str(exc)) from exc
        return review

    def create_intent(
        self,
        project_id: str,
        *,
        request: str,
        context: str,
        base_ref: str,
        created_by: str,
        candidates: list[InterpretationCandidate | dict],
    ) -> IntentMap:
        project = self.database.get_project(project_id)
        if len(candidates) < 2:
            raise ValueError("an intent requires at least two candidate interpretations")
        repository = GitRepository(project.repo_path)
        resolved_base = repository.resolve(base_ref)
        normalized_candidates = [
            item if isinstance(item, InterpretationCandidate) else InterpretationCandidate.model_validate(item)
            for item in candidates
        ]
        intent = IntentMap(
            project_id=project.id,
            request=request.strip(),
            context=context.strip(),
            base_ref=resolved_base,
            base_version=project.version,
            created_by=created_by.strip(),
            candidates=normalized_candidates,
        )
        self.database.save_intent(intent)
        return intent

    def clarify_intent(
        self,
        intent_id: str,
        *,
        actor: str,
        question: str,
        answer: str,
        retained_candidate_ids: list[str],
        eliminated_candidate_ids: list[str],
        resolved_uncertainties: dict[str, list[str]],
        candidate_revisions: dict[str, InterpretationCandidate | dict] | None = None,
        added_candidates: list[InterpretationCandidate | dict] | None = None,
        expected_revision: int,
    ) -> IntentMap:
        intent = self.database.get_intent(intent_id)
        if intent.revision != expected_revision:
            raise DecisionBlocked(
                f"stale intent state: expected revision {expected_revision}; current revision is {intent.revision}"
            )
        if intent.status in {"selected", "realized"}:
            raise DecisionBlocked("selected or realized intent cannot be clarified")
        before_ids = [item.id for item in intent.candidates if item.status == "active"]
        retained = set(retained_candidate_ids)
        eliminated = set(eliminated_candidate_ids)
        candidate_revisions = candidate_revisions or {}
        added_candidates = added_candidates or []
        if retained & eliminated:
            raise ValueError("a candidate cannot be both retained and eliminated")
        if not retained or retained | eliminated != set(before_ids):
            raise ValueError("clarification must disposition every active candidate and retain at least one")
        if not set(candidate_revisions).issubset(retained):
            raise ValueError("only retained candidates may be revised")
        revised_candidates = []
        for candidate in intent.candidates:
            replacement = candidate_revisions.get(candidate.id)
            updated = (
                replacement
                if isinstance(replacement, InterpretationCandidate)
                else InterpretationCandidate.model_validate(replacement)
                if replacement is not None
                else candidate.model_copy(deep=True)
            )
            if updated.id != candidate.id:
                raise ValueError("a clarification revision must preserve the candidate ID")
            if candidate.id in eliminated:
                updated.status = "eliminated"
            elif candidate.id in retained:
                updated.status = "active"
                resolved = set(resolved_uncertainties.get(candidate.id, []))
                unknown = resolved - set(updated.uncertainties)
                if unknown:
                    raise ValueError(f"clarification resolves unknown uncertainty for {candidate.id}")
                updated.uncertainties = [
                    item for item in updated.uncertainties if item not in resolved
                ]
            revised_candidates.append(updated)
        known_ids = {item.id for item in revised_candidates}
        normalized_added = [
            item if isinstance(item, InterpretationCandidate) else InterpretationCandidate.model_validate(item)
            for item in added_candidates
        ]
        if any(item.id in known_ids for item in normalized_added):
            raise ValueError("added clarification candidates require new IDs")
        revised_candidates.extend(normalized_added)
        after_ids = [item.id for item in revised_candidates if item.status == "active"]
        next_revision = intent.revision + 1
        clarification = ClarificationRecord(
            intent_revision=next_revision,
            question=question.strip(),
            answer=answer.strip(),
            actor=actor.strip(),
            before_candidate_ids=before_ids,
            after_candidate_ids=after_ids,
            eliminated_candidate_ids=list(eliminated_candidate_ids),
            revised_candidate_ids=list(candidate_revisions),
            added_candidate_ids=[item.id for item in normalized_added],
            resolved_uncertainties=resolved_uncertainties,
            before_candidates=[item.model_copy(deep=True) for item in intent.candidates],
            after_candidates=[item.model_copy(deep=True) for item in revised_candidates],
        )
        updated_intent = intent.model_copy(deep=True)
        updated_intent.revision = next_revision
        updated_intent.candidates = revised_candidates
        updated_intent.clarification_history.append(clarification)
        updated_intent.status = (
            "ready_for_selection"
            if len(after_ids) == 1
            and not next(item for item in revised_candidates if item.id == after_ids[0]).uncertainties
            else "clarification_required"
        )
        updated_intent.updated_at = datetime.now(UTC)
        try:
            self.database.apply_intent_transition(
                updated_intent, expected_revision=expected_revision
            )
        except ConcurrentTransitionError as exc:
            raise DecisionBlocked(str(exc)) from exc
        return updated_intent

    def select_intent_candidate(
        self,
        intent_id: str,
        *,
        candidate_id: str,
        actor: str,
        reason: str,
        expected_revision: int,
    ) -> IntentMap:
        intent = self.database.get_intent(intent_id)
        if intent.revision != expected_revision:
            raise DecisionBlocked(
                f"stale intent state: expected revision {expected_revision}; current revision is {intent.revision}"
            )
        if intent.status not in {"ready_for_selection", "clarification_required"}:
            raise DecisionBlocked("intent is not open for candidate selection")
        chosen = next(
            (item for item in intent.candidates if item.id == candidate_id and item.status == "active"),
            None,
        )
        if chosen is None:
            raise ValueError("selected candidate is not active in this intent")
        if chosen.uncertainties:
            raise DecisionBlocked("selected candidate still has unresolved uncertainty")
        updated_intent = intent.model_copy(deep=True)
        for candidate in updated_intent.candidates:
            if candidate.id == candidate_id:
                candidate.status = "selected"
            elif candidate.status == "active":
                candidate.status = "not_selected"
        updated_intent.revision += 1
        updated_intent.status = "selected"
        updated_intent.selected_candidate_id = candidate_id
        updated_intent.selection_actor = actor.strip()
        updated_intent.selection_reason = reason.strip()
        updated_intent.selected_at = datetime.now(UTC)
        updated_intent.updated_at = updated_intent.selected_at
        try:
            self.database.apply_intent_transition(
                updated_intent, expected_revision=expected_revision
            )
        except ConcurrentTransitionError as exc:
            raise DecisionBlocked(str(exc)) from exc
        return updated_intent

    @staticmethod
    def _structural_delta_distance(
        predicted: PythonImportSubstitution,
        observed: PythonImportSubstitution,
    ) -> float:
        fields = ("path", "from_module", "to_module")
        mismatches = sum(getattr(predicted, field) != getattr(observed, field) for field in fields)
        return mismatches / len(fields)

    def realize_intent(
        self,
        intent_id: str,
        *,
        actor: str,
        expected_revision: int,
    ) -> IntentMap:
        intent = self.database.get_intent(intent_id)
        if intent.revision != expected_revision:
            raise DecisionBlocked(
                f"stale intent state: expected revision {expected_revision}; current revision is {intent.revision}"
            )
        if intent.status != "selected" or not intent.selected_candidate_id:
            raise DecisionBlocked("only an explicitly selected interpretation may enter Phi")
        if any(item.status == "succeeded" for item in intent.realization_attempts):
            raise DecisionBlocked("this intent already has a successful realization")
        project = self.database.get_project(intent.project_id)
        if project.version != intent.base_version:
            raise DecisionBlocked(
                f"intent base is stale: expected C^{intent.base_version}; current state is C^{project.version}"
            )
        repository = GitRepository(project.repo_path)
        if repository.resolve(project.head_ref) != intent.base_ref:
            raise DecisionBlocked("project head no longer matches the selected intent base")
        selected = next(
            item for item in intent.candidates if item.id == intent.selected_candidate_id
        )
        delta = selected.structural_delta
        realization_id = new_id("realization")
        phi = repository.realize_python_import_substitution(
            intent.base_ref,
            path=delta.path,
            from_module=delta.from_module,
            to_module=delta.to_module,
            proposal_id=f"{intent.id}-{realization_id}",
        )
        updated_intent = intent.model_copy(deep=True)
        updated_intent.revision += 1
        updated_intent.updated_at = datetime.now(UTC)
        if phi.target_ref is None:
            updated_intent.realization_attempts.append(
                RealizationRecord(
                    id=realization_id,
                    status="failed",
                    intent_id=intent.id,
                    candidate_id=selected.id,
                    base_ref=intent.base_ref,
                    predicted_delta=delta,
                    failed_preconditions=phi.failed_preconditions,
                    actor=actor.strip(),
                )
            )
            try:
                self.database.apply_intent_transition(
                    updated_intent, expected_revision=expected_revision
                )
            except ConcurrentTransitionError as exc:
                raise DecisionBlocked(str(exc)) from exc
            return updated_intent

        persisted = False
        try:
            rehydrated, unobservable = rehydrate_python_import_substitutions(
                repository, intent.base_ref, phi.target_ref
            )
            matching = next(
                (item for item in rehydrated if item.structural_delta == delta),
                None,
            )
            chosen_rehydration = matching or (
                max(rehydrated, key=lambda item: item.confidence) if rehydrated else None
            )
            discrepancy = (
                self._structural_delta_distance(delta, chosen_rehydration.structural_delta)
                if chosen_rehydration
                else 1.0
            )
            coverage = 1.0 if chosen_rehydration and not unobservable else 0.0
            record = RealizationRecord(
                id=realization_id,
                status="succeeded",
                intent_id=intent.id,
                candidate_id=selected.id,
                base_ref=intent.base_ref,
                target_ref=phi.target_ref,
                git_ref=phi.git_ref,
                predicted_delta=delta,
                artifact_diff=phi.artifact_diff,
                failed_preconditions=phi.failed_preconditions,
                rehydrated_candidates=rehydrated,
                selected_rehydration_id=chosen_rehydration.id if chosen_rehydration else None,
                unobservable_relations=unobservable,
                round_trip_discrepancy=discrepancy,
                observable_coverage=coverage,
                actor=actor.strip(),
            )
            review, review_event = self._build_review(
                project.id,
                base_ref=intent.base_ref,
                target_ref=phi.target_ref,
                proposer=actor.strip(),
                intent_summary=intent.request,
                intent_id=intent.id,
                selected_interpretation_id=selected.id,
                realization_id=record.id,
                rehydrated_deltas=rehydrated,
                round_trip_discrepancy=discrepancy,
                observable_coverage=coverage,
            )
            record.review_id = review.id
            updated_intent.realization_attempts.append(record)
            updated_intent.realized_review_id = review.id
            updated_intent.status = "realized"
            for candidate in updated_intent.candidates:
                if candidate.id == selected.id:
                    candidate.status = "realized"
            try:
                self.database.apply_realization_transition(
                    intent=updated_intent,
                    review=review,
                    event=review_event,
                    expected_intent_revision=expected_revision,
                )
            except (ConcurrentTransitionError, DuplicateReviewRecordError) as exc:
                raise DecisionBlocked(str(exc)) from exc
            persisted = True
        finally:
            if phi.git_ref and phi.target_ref:
                if not persisted:
                    repository.delete_proposal_ref(phi.git_ref, phi.target_ref)
        return updated_intent

    def build_trust_root_possession_template(
        self,
        project_id: str,
        *,
        new_root: AttestationTrustRoot | dict,
    ) -> dict:
        """Describe the exact DSSE message an incoming verifier key must sign."""
        project = self.database.get_project(project_id)
        root = AttestationTrustRoot.model_validate(new_root)
        if root.status != "active" or not root.accepts_new_attestations():
            raise DecisionBlocked("the new trust root is not currently valid")
        return build_possession_template(
            root,
            project_head=project.head_ref,
            project_version=project.version,
        )

    def grant_trust_administrator(
        self,
        project_id: str,
        *,
        actor: str,
        reason: str,
        expected_project_version: int,
    ) -> Project:
        """Extend an existing decision owner's grant for an explicit local upgrade."""
        project = self.database.get_project(project_id)
        if project.version != expected_project_version:
            raise DecisionBlocked(
                "stale project state: "
                f"expected C^{expected_project_version}; current state is C^{project.version}"
            )
        normalized_actor = actor.strip()
        if not normalized_actor:
            raise DecisionBlocked("an identified trust administrator is required")
        if not reason or len(reason.strip()) < 8:
            raise DecisionBlocked("a substantive trust-administration rationale is required")
        actor_key = normalized_actor.casefold()
        grant_index = next(
            (
                index
                for index, grant in enumerate(project.authority_grants)
                if grant.authority == project.default_authority
                and "commit" in grant.actions
                and actor_key in {candidate.strip().casefold() for candidate in grant.actors}
            ),
            None,
        )
        if grant_index is None:
            raise DecisionBlocked(
                "trust administration can only extend an existing commit authority"
            )
        if "manage_trust" in project.authority_grants[grant_index].actions:
            raise DecisionBlocked("this actor already has trust administration authority")

        updated = project.model_copy(deep=True)
        updated.authority_grants[grant_index].actions.append("manage_trust")
        updated.version = expected_project_version + 1
        event = ProjectAuditEvent(
            project_id=project.id,
            project_version=updated.version,
            action="authority_grant_extend",
            actor=normalized_actor,
            authority=project.default_authority,
            policy_id=project.policy_id,
            reason=reason.strip(),
            payload={
                "actor": normalized_actor,
                "authority": project.default_authority,
                "granted_action": "manage_trust",
            },
        )
        try:
            self.database.apply_project_transition(
                project=updated,
                event=event,
                expected_project_version=expected_project_version,
            )
        except ConcurrentTransitionError as exc:
            raise DecisionBlocked(str(exc)) from exc
        return updated

    def grant_authority_actor(
        self,
        project_id: str,
        *,
        authorizer: str,
        target_actor: str,
        reason: str,
        expected_project_version: int,
    ) -> Project:
        """Add one registered local identity to an existing authority grant."""
        project = self.database.get_project(project_id)
        if project.version != expected_project_version:
            raise DecisionBlocked(
                "stale project state: "
                f"expected C^{expected_project_version}; current state is C^{project.version}"
            )
        normalized_authorizer = authorizer.strip()
        normalized_target = target_actor.strip()
        if not normalized_authorizer or not normalized_target:
            raise DecisionBlocked("identified authority actors are required")
        if not reason or len(reason.strip()) < 8:
            raise DecisionBlocked("a substantive authority-delegation rationale is required")

        authorizer_key = normalized_authorizer.casefold()
        grant_index = next(
            (
                index
                for index, grant in enumerate(project.authority_grants)
                if grant.authority == project.default_authority
                and "manage_trust" in grant.actions
                and authorizer_key
                in {candidate.strip().casefold() for candidate in grant.actors}
            ),
            None,
        )
        if grant_index is None:
            raise DecisionBlocked(
                "the authorizer is not permitted to manage project authority"
            )

        target_key = normalized_target.casefold()
        target_user = next(
            (
                user
                for user in self.database.list_auth_users()
                if user["actor_normalized"] == target_key and not user["disabled"]
            ),
            None,
        )
        if target_user is None:
            raise DecisionBlocked(
                "authority can only be granted to a registered active local identity"
            )
        if target_key in {
            candidate.strip().casefold()
            for grant in project.authority_grants
            if grant.authority == project.default_authority
            for candidate in grant.actors
        }:
            raise DecisionBlocked("this actor already holds the project authority")

        updated = project.model_copy(deep=True)
        updated.authority_grants[grant_index].actors.append(target_user["actor"])
        updated.version = expected_project_version + 1
        event = ProjectAuditEvent(
            project_id=project.id,
            project_version=updated.version,
            action="authority_actor_add",
            actor=normalized_authorizer,
            authority=project.default_authority,
            policy_id=project.policy_id,
            reason=reason.strip(),
            payload={
                "target_actor": target_user["actor"],
                "authority": project.default_authority,
                "granted_actions": list(
                    updated.authority_grants[grant_index].actions
                ),
            },
        )
        try:
            self.database.apply_project_transition(
                project=updated,
                event=event,
                expected_project_version=expected_project_version,
            )
        except ConcurrentTransitionError as exc:
            raise DecisionBlocked(str(exc)) from exc
        return updated

    def change_trust_roots(
        self,
        project_id: str,
        *,
        action: str,
        actor: str,
        authority: str,
        policy_id: str,
        reason: str,
        expected_project_version: int,
        new_root: AttestationTrustRoot | dict | None = None,
        new_key_proof: dict | None = None,
        key_id: str | None = None,
        revocation_mode: str = "prospective",
        confirm_retroactive: bool = False,
    ) -> Project:
        """Apply an authorized, versioned change to project attestation trust."""
        project = self.database.get_project(project_id)
        if project.version != expected_project_version:
            raise DecisionBlocked(
                "stale project state: "
                f"expected C^{expected_project_version}; current state is C^{project.version}"
            )
        normalized_actor = actor.strip()
        if not normalized_actor:
            raise DecisionBlocked("an identified trust administrator is required")
        if policy_id != project.policy_id:
            raise DecisionBlocked(f"trust change must use governing policy {project.policy_id}")
        if authority != project.default_authority:
            raise DecisionBlocked("asserted authority cannot manage project trust roots")
        if not reason or len(reason.strip()) < 8:
            raise DecisionBlocked("a substantive trust-change rationale is required")
        if project.authority_grants:
            normalized_actor_key = normalized_actor.casefold()
            grant = next(
                (
                    item
                    for item in project.authority_grants
                    if item.authority == authority
                    and "manage_trust" in item.actions
                    and normalized_actor_key
                    in {candidate.strip().casefold() for candidate in item.actors}
                ),
                None,
            )
            if grant is None:
                raise DecisionBlocked(
                    f"actor {normalized_actor} is not authorized as {authority} for manage_trust"
                )
        if (
            action in {"revoke", "rotate"}
            and revocation_mode == "retroactive"
            and not confirm_retroactive
        ):
            raise DecisionBlocked(
                "retroactive trust-root revocation requires explicit confirmation"
            )
        if action == "revoke":
            normalized_key_id = (key_id or "").strip()
            if not normalized_key_id:
                raise DecisionBlocked("the trust-root key ID to revoke is required")
            if revocation_mode not in {"prospective", "retroactive"}:
                raise DecisionBlocked("revocation mode must be prospective or retroactive")
            root_index = next(
                (
                    index
                    for index, item in enumerate(project.attestation_trust_roots)
                    if item.key_id == normalized_key_id
                ),
                None,
            )
            if root_index is None:
                raise DecisionBlocked(f"trust-root key ID {normalized_key_id} is unknown")
            current_root = project.attestation_trust_roots[root_index]
            if current_root.status != "active":
                raise DecisionBlocked(f"trust-root key ID {normalized_key_id} is already revoked")
            now = datetime.now(UTC)
            revoked_root = AttestationTrustRoot.model_validate(
                {
                    **current_root.model_dump(mode="python"),
                    "status": "revoked",
                    "valid_until": _revocation_valid_until(current_root, now),
                    "revoked_at": now,
                    "revoked_by": normalized_actor,
                    "revoked_under_policy": policy_id,
                    "revocation_reason": reason.strip(),
                    "revocation_mode": revocation_mode,
                }
            )
            updated = project.model_copy(deep=True)
            updated.attestation_trust_roots[root_index] = revoked_root
            updated.version = expected_project_version + 1
            event = ProjectAuditEvent(
                project_id=project.id,
                project_version=updated.version,
                action="trust_root_revoke",
                actor=normalized_actor,
                authority=authority,
                policy_id=policy_id,
                reason=reason.strip(),
                payload={
                    "key_id": revoked_root.key_id,
                    "verifier_id": revoked_root.verifier_id,
                    "revocation_mode": revocation_mode,
                },
            )
            try:
                self.database.apply_project_transition(
                    project=updated,
                    event=event,
                    expected_project_version=expected_project_version,
                )
            except ConcurrentTransitionError as exc:
                raise DecisionBlocked(str(exc)) from exc
            return updated

        if action not in {"add", "rotate"}:
            raise DecisionBlocked(f"unsupported trust-root action: {action}")
        if new_root is None:
            raise DecisionBlocked("a new trust root is required")
        if new_key_proof is None:
            raise DecisionBlocked("proof of possession for the new trust root is required")

        root = AttestationTrustRoot.model_validate(new_root)
        if root.status != "active":
            raise DecisionBlocked("a new trust root must be active")
        if not root.accepts_new_attestations():
            raise DecisionBlocked("the new trust root is not currently valid")
        if any(item.key_id == root.key_id for item in project.attestation_trust_roots):
            raise DecisionBlocked(f"trust-root key ID {root.key_id} has already been used")
        if any(
            item.public_key_base64 == root.public_key_base64
            for item in project.attestation_trust_roots
        ):
            raise DecisionBlocked("this trust-root public key has already been used")
        try:
            verified = verify_dsse_vsa(
                new_key_proof,
                trust_roots=[root],
                expected_git_commit=project.head_ref,
                required_verifier_id=root.verifier_id,
                required_verified_level=TRUST_ROOT_POSSESSION_LEVEL,
                required_policy_uri=TRUST_ROOT_POSSESSION_POLICY_URI,
            )
        except AttestationVerificationError as exc:
            raise DecisionBlocked(f"new trust-root possession proof is invalid: {exc}") from exc

        now = datetime.now(UTC)
        added_root = AttestationTrustRoot.model_validate(
            {
                **root.model_dump(mode="python"),
                "status": "active",
                "added_at": now,
                "added_by": normalized_actor,
                "added_under_policy": policy_id,
            }
        )
        updated = project.model_copy(deep=True)
        event_action = "trust_root_add"
        event_payload = {
            "key_id": added_root.key_id,
            "verifier_id": added_root.verifier_id,
            "proof_envelope_sha256": verified.envelope_sha256,
            "proof_envelope": deepcopy(new_key_proof),
        }
        if action == "rotate":
            normalized_key_id = (key_id or "").strip()
            if not normalized_key_id:
                raise DecisionBlocked("the trust-root key ID to rotate is required")
            if revocation_mode not in {"prospective", "retroactive"}:
                raise DecisionBlocked("revocation mode must be prospective or retroactive")
            root_index = next(
                (
                    index
                    for index, item in enumerate(project.attestation_trust_roots)
                    if item.key_id == normalized_key_id
                ),
                None,
            )
            if root_index is None:
                raise DecisionBlocked(f"trust-root key ID {normalized_key_id} is unknown")
            current_root = project.attestation_trust_roots[root_index]
            if current_root.status != "active":
                raise DecisionBlocked(f"trust-root key ID {normalized_key_id} is already revoked")
            revoked_root = AttestationTrustRoot.model_validate(
                {
                    **current_root.model_dump(mode="python"),
                    "status": "revoked",
                    "valid_until": _revocation_valid_until(current_root, now),
                    "revoked_at": now,
                    "revoked_by": normalized_actor,
                    "revoked_under_policy": policy_id,
                    "revocation_reason": reason.strip(),
                    "revocation_mode": revocation_mode,
                }
            )
            updated.attestation_trust_roots[root_index] = revoked_root
            event_action = "trust_root_rotate"
            event_payload = {
                "old_key_id": revoked_root.key_id,
                "new_key_id": added_root.key_id,
                "verifier_id": added_root.verifier_id,
                "revocation_mode": revocation_mode,
                "proof_envelope_sha256": verified.envelope_sha256,
                "proof_envelope": deepcopy(new_key_proof),
            }
        updated.attestation_trust_roots.append(added_root)
        updated.version = expected_project_version + 1
        event = ProjectAuditEvent(
            project_id=project.id,
            project_version=updated.version,
            action=event_action,
            actor=normalized_actor,
            authority=authority,
            policy_id=policy_id,
            reason=reason.strip(),
            payload=event_payload,
        )
        try:
            self.database.apply_project_transition(
                project=updated,
                event=event,
                expected_project_version=expected_project_version,
            )
        except ConcurrentTransitionError as exc:
            raise DecisionBlocked(str(exc)) from exc
        return updated

    def _build_review(
        self,
        project_id: str,
        *,
        base_ref: str,
        target_ref: str,
        proposer: str = "coding-agent",
        intent_summary: str = "",
        external_url: str | None = None,
        external_label: str | None = None,
        intent_id: str | None = None,
        selected_interpretation_id: str | None = None,
        realization_id: str | None = None,
        rehydrated_deltas: list[RehydratedDeltaCandidate] | None = None,
        round_trip_discrepancy: float | None = None,
        observable_coverage: float | None = None,
    ) -> tuple[ReviewPackage, AuditEvent]:
        project = self.database.get_project(project_id)
        repository = GitRepository(project.repo_path)
        resolved_base = repository.resolve(base_ref)
        resolved_target = repository.resolve(target_ref)
        duplicate = next(
            (
                review
                for review in self.database.list_reviews(project.id)
                if review.base_ref == resolved_base
                and review.target_ref == resolved_target
                and review.status in {"open", "committed"}
            ),
            None,
        )
        if duplicate is not None:
            raise DuplicateReviewError(f"review for these revisions already exists: {duplicate.id}")
        findings = []
        for claim in project.claims:
            findings.extend(
                analyze_python_imports(
                    repository,
                    resolved_base,
                    resolved_target,
                    rule_id=claim.id,
                    forbidden_modules=claim.forbidden_modules,
                    severity=claim.severity,
                )
            )
        changed_paths = set(repository.changed_files(resolved_base, resolved_target))
        overlapping_reviews: list[str] = []
        overlapping_paths: set[str] = set()
        for existing in self.database.list_reviews(project.id):
            if existing.status != "open":
                continue
            existing_paths = set(repository.changed_files(existing.base_ref, existing.target_ref))
            shared = changed_paths & existing_paths
            if shared:
                overlapping_reviews.append(existing.id)
                overlapping_paths.update(shared)
        if overlapping_reviews:
            findings.append(
                Finding(
                    rule_id="system.concurrent_change_overlap",
                    kind="overlap",
                    severity="warning",
                    message=f"This proposal overlaps {_count_phrase(len(overlapping_reviews), 'open review package')}",
                    details={"reviews": overlapping_reviews, "paths": sorted(overlapping_paths)},
                )
            )
        claim_ids = sorted(
            {
                finding.rule_id
                for finding in findings
                if any(claim.id == finding.rule_id for claim in project.claims)
            }
        )
        static_failed = any(item.kind == "syntax_error" for item in findings)
        if any(item.kind == "forbidden_dependency" for item in findings):
            static_outcome = "contests"
        elif any(item.kind == "unobservable" for item in findings):
            static_outcome = "inconclusive"
        else:
            static_outcome = "supports"

        test_evidence = run_tests(project.repo_path, project.test_command, target_ref=resolved_target)
        test_evidence.artifact_ref = resolved_target
        test_evidence.provenance = "isolated_target_checkout"
        test_evidence.outcome = (
            "supports" if test_evidence.status == "pass" else "inconclusive" if test_evidence.status == "not_run" else "contests"
        )
        evidence = [
            Evidence(
                kind="git",
                status="pass",
                outcome="supports",
                summary="Both Git revisions resolved",
                artifact_ref=resolved_target,
                provenance="git_revision_resolution",
                details={"base": resolved_base, "target": resolved_target},
            ),
            Evidence(
                kind="static_analysis",
                status="fail" if static_failed else "pass",
                outcome=static_outcome,
                summary=self._static_summary(findings, len(project.claims)),
                claim_ids=claim_ids,
                artifact_ref=resolved_target,
                provenance="python_ast",
                details={
                    "finding_ids": [item.id for item in findings if item.rule_id in claim_ids],
                    "changed_paths": sorted(changed_paths),
                },
            ),
            test_evidence,
        ]
        claim_deltas = self._claim_deltas(project.claims, findings, resolved_target)
        observable = [item for item in claim_deltas if item.status != "unobservable"]
        claim_observable_coverage = len(observable) / len(claim_deltas) if claim_deltas else None
        review = ReviewPackage(
            project_id=project.id,
            base_ref=resolved_base,
            target_ref=resolved_target,
            base_version=project.version,
            current_project_version=project.version,
            intent_summary=intent_summary.strip(),
            intent_id=intent_id,
            selected_interpretation_id=selected_interpretation_id,
            realization_id=realization_id,
            proposer=proposer.strip() or "coding-agent",
            external_url=external_url,
            external_label=external_label,
            patch_summary=repository.diff_stat(resolved_base, resolved_target) or "No file-level changes",
            changed_paths=sorted(changed_paths),
            claim_deltas=claim_deltas,
            rehydrated_deltas=rehydrated_deltas or [],
            round_trip_discrepancy=round_trip_discrepancy,
            observable_coverage=(
                observable_coverage
                if observable_coverage is not None
                else claim_observable_coverage
            ),
            evidence_obligations=[
                obligation.model_copy(deep=True)
                for claim in project.claims
                if any(delta.claim_id == claim.id for delta in claim_deltas)
                for obligation in claim.evidence_obligations
            ],
            summary=self._deterministic_summary(findings, evidence),
            findings=findings,
            evidence=evidence,
            governing_policy=project.policy_id,
            required_authorities=self._required_authorities(project, claim_deltas),
        )
        event = AuditEvent(
            review_id=review.id,
            action="create_review",
            actor="system",
            payload={
                "base_ref": resolved_base,
                "target_ref": resolved_target,
                "proposer": review.proposer,
                "intent_summary": review.intent_summary,
                "external_url": review.external_url,
                "external_label": review.external_label,
                "intent_id": review.intent_id,
                "selected_interpretation_id": review.selected_interpretation_id,
                "realization_id": review.realization_id,
            },
        )
        commitments.bind_baseline(review, project)
        return review, event

    def create_review(
        self,
        project_id: str,
        *,
        base_ref: str,
        target_ref: str,
        proposer: str = "coding-agent",
        intent_summary: str = "",
        external_url: str | None = None,
        external_label: str | None = None,
        intent_id: str | None = None,
        selected_interpretation_id: str | None = None,
        realization_id: str | None = None,
        rehydrated_deltas: list[RehydratedDeltaCandidate] | None = None,
        round_trip_discrepancy: float | None = None,
        observable_coverage: float | None = None,
    ) -> ReviewPackage:
        review, event = self._build_review(
            project_id,
            base_ref=base_ref,
            target_ref=target_ref,
            proposer=proposer,
            intent_summary=intent_summary,
            external_url=external_url,
            external_label=external_label,
            intent_id=intent_id,
            selected_interpretation_id=selected_interpretation_id,
            realization_id=realization_id,
            rehydrated_deltas=rehydrated_deltas,
            round_trip_discrepancy=round_trip_discrepancy,
            observable_coverage=observable_coverage,
        )
        try:
            self.database.create_review(review, event)
        except DuplicateReviewRecordError as exc:
            raise DuplicateReviewError(str(exc)) from exc
        return review

    def rerun_tests(
        self,
        review_id: str,
        *,
        test_command: list[str],
        actor: str,
    ) -> ReviewPackage:
        review = self.database.get_review(review_id)
        project = self.database.get_project(review.project_id)
        if review.status != "open":
            raise DecisionBlocked(f"cannot rerun tests for a review in {review.status} status")
        normalized_command = [part.strip() for part in test_command]
        if not normalized_command or any(not part for part in normalized_command):
            raise DecisionBlocked("a non-empty test command is required")
        configured_command = [part.strip() for part in project.test_command]
        if configured_command and normalized_command != configured_command:
            raise DecisionBlocked(
                "the test command is fixed by project intake and cannot be replaced mid-review"
            )

        test_evidence = run_tests(
            project.repo_path,
            normalized_command,
            target_ref=review.target_ref,
        )
        test_evidence.artifact_ref = review.target_ref
        test_evidence.provenance = "isolated_target_checkout"
        test_evidence.outcome = (
            "supports"
            if test_evidence.status == "pass"
            else "inconclusive"
            if test_evidence.status == "not_run"
            else "contests"
        )

        next_review = review.model_copy(deep=True)
        next_review.evidence = [
            item for item in next_review.evidence if item.kind != "tests"
        ] + [test_evidence]
        next_review.summary = self._deterministic_summary(
            next_review.findings, next_review.evidence
        )
        expected_review_revision = review.revision
        next_review.revision = expected_review_revision + 1
        next_review.updated_at = datetime.now(UTC)
        event = AuditEvent(
            review_id=review.id,
            action="rerun_tests",
            actor=actor,
            payload={
                "test_command": normalized_command,
                "evidence_id": test_evidence.id,
                "status": test_evidence.status,
            },
        )

        self.database.apply_review_transition(
            review=next_review,
            event=event,
            expected_review_revision=expected_review_revision,
        )
        return next_review

    @staticmethod
    def _static_summary(findings: list[Finding], claim_count: int) -> str:
        syntax_errors = sum(item.kind == "syntax_error" for item in findings)
        contested = sum(item.kind == "forbidden_dependency" for item in findings)
        unobservable = sum(item.kind == "unobservable" for item in findings)
        if syntax_errors:
            return f"Analysis failed on {_count_phrase(syntax_errors, 'changed Python file')}"
        if contested:
            return f"Analysis completed; {_count_phrase(contested, 'structural claim violation')} found"
        if unobservable:
            relation = _count_phrase(unobservable, "relation")
            return f"Analysis completed; {relation} {'remains' if unobservable == 1 else 'remain'} unobservable"
        claim = _count_phrase(claim_count, "structural claim")
        return f"Analysis completed; {claim} {'remains' if claim_count == 1 else 'remain'} uncontested"

    @staticmethod
    def _claim_deltas(
        claims: list[StructuralClaim], findings: list[Finding], target_ref: str
    ) -> list[ClaimDelta]:
        deltas: list[ClaimDelta] = []
        for claim in claims:
            related = [item for item in findings if item.rule_id == claim.id]
            if not related:
                continue
            unobservable = any(item.kind == "unobservable" for item in related)
            anchors = [
                ArtifactAnchor(
                    path=item.path or "project",
                    line=item.line,
                    kind="code",
                    relation="observes" if unobservable else "contests",
                    version_ref=target_ref,
                )
                for item in related
                if item.path
            ]
            deltas.append(
                ClaimDelta(
                    claim_id=claim.id,
                    operation="contest",
                    status="unobservable" if unobservable else "contested",
                    summary=(
                        f"Artifact change leaves ‘{claim.title}’ unresolved"
                        if unobservable
                        else f"Artifact change contests ‘{claim.title}’"
                    ),
                    affected_scope=claim.scope,
                    before=claim.title,
                    after="Relationship cannot be established from current evidence" if unobservable else related[0].message,
                    artifact_anchors=anchors,
                    source="rehydrated",
                    confidence=None if unobservable else 1.0,
                )
            )
        return deltas

    def get_contract_graph(self, review_id: str) -> ContractGraph:
        """Project one review into a versioned, reviewer-safe relation graph."""
        review = self.database.get_review(review_id)
        project = self.database.get_project(review.project_id)
        nodes: dict[str, ContractGraphNode] = {}
        edges: list[ContractGraphEdge] = []
        edge_keys: set[tuple[str, str, str]] = set()

        def add_node(
            node_id: str,
            node_type: str,
            label: str,
            status: str,
            summary: str = "",
            metadata: dict | None = None,
        ) -> None:
            if node_id in nodes:
                return
            nodes[node_id] = ContractGraphNode(
                id=node_id,
                type=node_type,
                label=label,
                status=status,
                summary=summary,
                metadata=metadata or {},
            )

        def add_edge(source: str, target: str, relation: str) -> None:
            key = (source, target, relation)
            if source not in nodes or target not in nodes or key in edge_keys:
                return
            edge_keys.add(key)
            edges.append(
                ContractGraphEdge(
                    id=f"edge:{len(edges) + 1:03d}",
                    source=source,
                    target=target,
                    relation=relation,
                    label=relation.replace("_", " "),
                )
            )

        add_node(
            "state:base",
            "base_state",
            f"C^{review.base_version}",
            "committed",
            "Governed state from which the proposal was evaluated",
            {"version": review.base_version, "revision": review.base_ref},
        )
        add_node(
            "state:proposal",
            "proposal",
            review.intent_summary or "Agent proposal",
            review.status,
            f"Proposed by {review.proposer}",
            {"proposer": review.proposer, "target_revision": review.target_ref},
        )
        add_node(
            "state:current",
            "current_state",
            f"C^{project.version}",
            review.status,
            "Current governed project state",
            {
                "project_version": project.version,
                "review_transition_version": review.current_project_version,
                "head_revision": project.head_ref,
            },
        )
        if review.intent_id:
            intent = self.database.get_intent(review.intent_id)
            add_node(
                f"intent:{intent.id}",
                "intent",
                intent.request,
                intent.status,
                intent.context,
                {
                    "base_version": intent.base_version,
                    "base_ref": intent.base_ref,
                    "revision": intent.revision,
                    "created_by": intent.created_by,
                    "clarification_turns": len(intent.clarification_history),
                },
            )
            selected = next(
                (
                    item
                    for item in intent.candidates
                    if item.id == review.selected_interpretation_id
                ),
                None,
            )
            if selected:
                interpretation_id = f"interpretation:{selected.id}"
                add_node(
                    interpretation_id,
                    "interpretation",
                    selected.title,
                    selected.status,
                    selected.summary,
                    {
                        "path": selected.structural_delta.path,
                        "from_module": selected.structural_delta.from_module,
                        "to_module": selected.structural_delta.to_module,
                        "uncertainties": selected.uncertainties,
                        "confidence": selected.confidence,
                        "provenance": selected.provenance,
                        "selection_actor": intent.selection_actor,
                        "selection_reason": intent.selection_reason,
                    },
                )
                add_edge(f"intent:{intent.id}", interpretation_id, "selects")
            realization = next(
                (
                    item
                    for item in intent.realization_attempts
                    if item.id == review.realization_id
                ),
                None,
            )
            if realization:
                realization_id = f"realization:{realization.id}"
                add_node(
                    realization_id,
                    "realization",
                    "Bounded Python import realization",
                    realization.status,
                    realization.operator,
                    {
                        "base_ref": realization.base_ref,
                        "target_ref": realization.target_ref,
                        "git_ref": realization.git_ref,
                        "actor": realization.actor,
                        "provenance": realization.provenance,
                        "round_trip_discrepancy": realization.round_trip_discrepancy,
                        "observable_coverage": realization.observable_coverage,
                    },
                )
                if selected:
                    add_edge(
                        f"interpretation:{selected.id}", realization_id, "realizes"
                    )
                for candidate in realization.rehydrated_candidates:
                    rehydration_id = f"rehydration:{candidate.id}"
                    add_node(
                        rehydration_id,
                        "rehydration",
                        (
                            f"{candidate.structural_delta.from_module} → "
                            f"{candidate.structural_delta.to_module}"
                        ),
                        (
                            "selected"
                            if candidate.id == realization.selected_rehydration_id
                            else "candidate"
                        ),
                        "Artifact-derived structural interpretation",
                        {
                            "path": candidate.structural_delta.path,
                            "confidence": candidate.confidence,
                            "provenance": candidate.provenance,
                            "evidence": candidate.evidence,
                        },
                    )
                    add_edge(realization_id, rehydration_id, "rehydrates")
                    if candidate.id == realization.selected_rehydration_id:
                        add_edge(
                            rehydration_id,
                            "state:proposal",
                            (
                                "round_trip_matches"
                                if realization.round_trip_discrepancy == 0
                                else "round_trip_diverges"
                            ),
                        )
        add_edge("state:base", "state:proposal", "proposes")

        claim_ids: set[str] = set()
        for claim in sorted(project.claims, key=lambda item: item.id):
            claim_id = f"claim:{claim.id}"
            claim_ids.add(claim.id)
            add_node(
                claim_id,
                "claim",
                claim.title,
                claim.status,
                claim.rationale,
                {
                    "claim_id": claim.id,
                    "scope": claim.scope,
                    "authority": claim.authority,
                    "introduced_version": claim.introduced_version,
                },
            )
            add_edge("state:current", claim_id, "governs")

        manual_claims = {item.id: item for item in review.commitment_baseline}
        manual_claims.update({change.after.id: change.after for change in review.commitment_changes})
        proposed_ids = {change.after.id for change in review.commitment_changes}
        for item in manual_claims.values():
            claim_ids.add(item.id)
            add_node(f"claim:{item.id}", "claim", item.title,
                "proposed" if item.id in proposed_ids else "recorded",
                item.statement, {"claim_id": item.id, "source": "human_authored_commitment",
                    "verification": item.verification, "category": item.category})
            add_edge("state:proposal" if item.id in proposed_ids else "state:base",
                f"claim:{item.id}", "proposes" if item.id in proposed_ids else "governs")

        artifact_paths = set(review.changed_paths)
        for item in manual_claims.values():
            artifact_paths.update(item.paths)
        for claim in project.claims:
            artifact_paths.update(anchor.path for anchor in claim.artifact_anchors)
        for delta in review.claim_deltas:
            artifact_paths.update(anchor.path for anchor in delta.artifact_anchors)
        artifact_paths.update(
            finding.path for finding in review.findings if finding.path
        )
        for path in sorted(artifact_paths):
            add_node(
                f"artifact:{path}",
                "artifact",
                path,
                "changed" if path in review.changed_paths else "context",
                "Changed artifact" if path in review.changed_paths else "Governed artifact context",
                {"path": path, "changed": path in review.changed_paths},
            )
            if path in review.changed_paths:
                add_edge("state:proposal", f"artifact:{path}", "changes")

        for item in manual_claims.values():
            for path in item.paths:
                add_edge(f"artifact:{path}", f"claim:{item.id}", "observes")
        for claim in sorted(project.claims, key=lambda item: item.id):
            for anchor in sorted(claim.artifact_anchors, key=lambda item: item.path):
                add_edge(
                    f"artifact:{anchor.path}",
                    f"claim:{claim.id}",
                    anchor.relation,
                )
        for delta in review.claim_deltas:
            if delta.claim_id not in claim_ids:
                continue
            for anchor in sorted(delta.artifact_anchors, key=lambda item: item.path):
                add_edge(
                    f"artifact:{anchor.path}",
                    f"claim:{delta.claim_id}",
                    anchor.relation,
                )

        evidence_relations = {
            "supports": "supports",
            "contests": "contests",
            "inconclusive": "inconclusive",
            "not_applicable": "inconclusive",
        }
        for evidence in review.evidence:
            node_id = f"evidence:{evidence.id}"
            add_node(
                node_id,
                "evidence",
                evidence.kind.replace("_", " ").title(),
                evidence.freshness if evidence.freshness != "current" else evidence.status,
                evidence.summary,
                {
                    "kind": evidence.kind,
                    "outcome": evidence.outcome,
                    "freshness": evidence.freshness,
                    "provenance": evidence.provenance,
                    "artifact_ref": evidence.artifact_ref,
                },
            )
            for claim_id in evidence.claim_ids:
                if claim_id in claim_ids:
                    add_edge(
                        node_id,
                        f"claim:{claim_id}",
                        evidence_relations[evidence.outcome],
                    )

        for finding in review.findings:
            node_id = f"finding:{finding.id}"
            add_node(
                node_id,
                "finding",
                finding.kind.replace("_", " ").title(),
                finding.status,
                finding.message,
                {
                    "severity": finding.severity,
                    "path": finding.path,
                    "line": finding.line,
                    "rule_id": finding.rule_id,
                },
            )
            if finding.path:
                add_edge(node_id, f"artifact:{finding.path}", "observes")
            if finding.rule_id in claim_ids:
                add_edge(node_id, f"claim:{finding.rule_id}", "contests")

        authority_data: dict[str, dict[str, list[str]]] = {}
        for grant in project.authority_grants:
            authority_data[grant.authority] = {
                "actors": sorted(grant.actors),
                "actions": sorted(grant.actions),
            }
        for authority in set(review.required_authorities) | {
            record.authority for record in review.decision_records
        }:
            authority_data.setdefault(authority, {"actors": [], "actions": []})
        for authority in sorted(authority_data):
            add_node(
                f"authority:{authority}",
                "authority",
                authority,
                "configured",
                f"Authority under {project.policy_id}",
                {
                    "policy_id": project.policy_id,
                    **authority_data[authority],
                },
            )
            for claim in project.claims:
                if claim.authority == authority:
                    add_edge(
                        f"authority:{authority}",
                        f"claim:{claim.id}",
                        "governs",
                    )

        decision_relations = {
            "commit": "commits",
            "waive": "waives",
            "rebase": "requires_rebase",
            "reject": "rejects",
            "rollback": "rolls_back",
        }
        for record in review.decision_records:
            node_id = f"decision:{record.id}"
            add_node(
                node_id,
                "decision",
                record.action.replace("_", " ").title(),
                "recorded",
                record.reason or "Decision recorded without an additional rationale",
                {
                    "actor": record.actor,
                    "authority": record.authority,
                    "policy_id": record.policy_id,
                    "provenance": record.provenance,
                    "created_at": record.created_at.isoformat(),
                },
            )
            add_edge(f"authority:{record.authority}", node_id, "authorizes")
            add_edge(node_id, "state:current", decision_relations[record.action])

        return ContractGraph(
            project_id=project.id,
            review_id=review.id,
            project_version=project.version,
            review_status=review.status,
            nodes=list(nodes.values()),
            edges=edges,
        )

    def get_change_package(self, review_id: str) -> ChangePackageManifest:
        review = self.database.get_review(review_id)
        project = self.database.get_project(review.project_id)
        obligation_statuses = evidence_obligation_statuses(
            review, trust_roots=project.attestation_trust_roots
        )
        unsatisfied_obligations = [
            item for item in obligation_statuses if item.status not in {"satisfied", "waived"}
        ]
        open_critical = open_critical_findings(review)
        base_current = review.base_version == project.version
        evidence_by_kind = {item.kind: item for item in review.evidence}
        static = evidence_by_kind.get("static_analysis")
        tests = evidence_by_kind.get("tests")
        retroactively_revoked_keys = {
            root.key_id
            for root in project.attestation_trust_roots
            if root.status == "revoked" and root.revocation_mode == "retroactive"
        }
        revoked_evidence = [
            item
            for item in review.evidence
            if item.details.get("key_id") in retroactively_revoked_keys
        ]
        stale_by_id = {
            item.id: item
            for item in [
                *[item for item in review.evidence if item.freshness == "stale"],
                *revoked_evidence,
            ]
        }
        stale = list(stale_by_id.values())
        overlaps = [item for item in review.findings if item.kind == "overlap" and item.status == "open"]
        committed = review.status == "committed"
        checks = [
            AdmissionCheck(
                key="base_version",
                label="Current base version",
                status="pass" if base_current or committed else "block",
                summary=(
                    f"Transition was admitted from C^{review.base_version} to C^{review.current_project_version}"
                    if committed
                    else f"Proposal is based on current C^{project.version}"
                    if base_current
                    else f"Proposal is based on C^{review.base_version}; current state is C^{project.version}"
                ),
            ),
            AdmissionCheck(
                key="static_analysis",
                label="Structural extraction completed",
                status="pass" if static and static.status == "pass" else "block",
                summary=static.summary if static else "Static analysis evidence is missing",
            ),
            AdmissionCheck(
                key="tests",
                label="Target tests passed",
                status="pass" if tests and tests.status == "pass" else "block",
                summary=tests.summary if tests else "Test evidence is missing",
            ),
            AdmissionCheck(
                key="critical_findings",
                label="Critical uncertainty resolved",
                status="block" if open_critical else "pass",
                summary=(
                    f"{_count_phrase(len(open_critical), 'open critical finding')} "
                    f"{'requires' if len(open_critical) == 1 else 'require'} disposition"
                    if open_critical
                    else "No critical findings remain open"
                ),
            ),
            AdmissionCheck(
                key="evidence_obligations",
                label="Declared evidence obligations",
                status="block" if unsatisfied_obligations else "pass",
                summary=(
                    f"{_count_phrase(len(unsatisfied_obligations), 'evidence obligation')} "
                    f"{'is' if len(unsatisfied_obligations) == 1 else 'are'} unsatisfied"
                    if unsatisfied_obligations
                    else "All declared evidence obligations are satisfied or waived"
                    if obligation_statuses
                    else "No evidence obligations are declared for this proposal"
                ),
            ),
            AdmissionCheck(
                key="evidence_freshness",
                label="Evidence is current",
                status="warn" if stale else "pass",
                summary=(
                    f"{_count_phrase(len(revoked_evidence), 'evidence record')} "
                    f"{'is' if len(revoked_evidence) == 1 else 'are'} invalid under a "
                    "retroactively revoked trust root"
                    if revoked_evidence
                    else f"{_count_phrase(len(stale), 'evidence record')} "
                    f"{'is' if len(stale) == 1 else 'are'} stale"
                    if stale
                    else "No stale evidence is attached"
                ),
            ),
            AdmissionCheck(
                key="proposal_conflict",
                label="Proposal conflicts resolved",
                status="warn" if overlaps else "pass",
                summary=(
                    f"Overlaps {_count_phrase(len(overlaps), 'open proposal')}"
                    if overlaps
                    else "No overlapping proposal is known"
                ),
            ),
            AdmissionCheck(
                key="human_authority",
                label="Human disposition",
                status="pass" if review.decision_records else "warn",
                summary=(
                    f"Decision recorded under {review.decision_records[-1].policy_id}"
                    if review.decision_records
                    else f"Requires {', '.join(review.required_authorities)} under {review.governing_policy}"
                ),
            ),
        ]
        blockers = [item.summary for item in checks if item.status == "block"] if review.status == "open" else []
        gate_state = (
            "ready"
            if review.status == "open" and not blockers
            else "blocked"
            if review.status == "open"
            else review.status
        )
        actions = {
            "open": ["commit", "waive", "rebase", "reject"],
            "committed": ["rollback"],
        }.get(review.status, [])
        return ChangePackageManifest(
            package_id=review.id,
            project_name=project.name,
            repo_label=project.repo_label or "registered://local-repository",
            intent_summary=review.intent_summary,
            proposer=review.proposer,
            notation={
                "v_t": review.base_version,
                "delta_c": len(review.claim_deltas),
                "delta_a": len(review.changed_paths),
                "delta_e": len(review.evidence),
                "unresolved": sum(item.status == "open" for item in review.findings),
                "waivers": len(review.waivers),
            },
            admission_checks=checks,
            obligation_statuses=obligation_statuses,
            invalidated_evidence_ids=[item.id for item in revoked_evidence],
            gate_state=gate_state,
            committable=review.status == "open" and not blockers,
            blockers=blockers,
            authority_actions=actions,
            governing_policy=review.governing_policy,
            required_authorities=review.required_authorities,
            decision_recorded=bool(review.decision_records),
        )

    def attach_evidence(
        self,
        review_id: str,
        *,
        actor: str,
        authority: str,
        policy_id: str,
        obligation_ids: list[str],
        summary: str,
        provenance: str,
    ) -> ReviewPackage:
        review = self.database.get_review(review_id)
        project = self.database.get_project(review.project_id)
        expected_project_version = project.version
        expected_review_revision = review.revision
        if review.status != "open":
            raise DecisionBlocked(f"cannot attach evidence to a review in {review.status} status")
        normalized_actor = actor.strip()
        if not normalized_actor:
            raise DecisionBlocked("an identified evidence recorder is required")
        authority, policy_id, _ = self._authorize_governed_action(
            project,
            review,
            actor=normalized_actor,
            authority=authority,
            policy_id=policy_id,
            action="attest",
        )
        normalized_summary = summary.strip()
        if len(normalized_summary) < 8:
            raise DecisionBlocked("a substantive evidence summary is required")
        normalized_provenance = provenance.strip()
        if not normalized_provenance:
            raise DecisionBlocked("evidence provenance is required")
        selected_ids = list(dict.fromkeys(item.strip() for item in obligation_ids if item.strip()))
        if not selected_ids:
            raise DecisionBlocked("at least one evidence obligation must be selected")
        obligation_by_id = {item.id: item for item in review.evidence_obligations}
        if any(item not in obligation_by_id for item in selected_ids):
            raise DecisionBlocked("evidence contains an unknown obligation")
        if any(obligation_by_id[item].verification != "authorized_record" for item in selected_ids):
            raise DecisionBlocked("this evidence obligation requires a verified DSSE attestation")
        provenance_mismatches = [
            obligation_by_id[item]
            for item in selected_ids
            if obligation_by_id[item].required_provenance_prefix
            and not normalized_provenance.startswith(
                obligation_by_id[item].required_provenance_prefix or ""
            )
        ]
        if provenance_mismatches:
            required = provenance_mismatches[0].required_provenance_prefix
            raise DecisionBlocked(f"evidence provenance must start with {required}")
        claim_ids = list(dict.fromkeys(obligation_by_id[item].claim_id for item in selected_ids))
        evidence = Evidence(
            kind="attestation",
            status="pass",
            outcome="supports",
            summary=normalized_summary,
            claim_ids=claim_ids,
            obligation_ids=selected_ids,
            artifact_ref=review.target_ref,
            provenance=normalized_provenance,
            recorded_by=normalized_actor,
            authority=authority,
            policy_id=policy_id,
            freshness="current",
        )
        next_review = review.model_copy(deep=True)
        next_review.evidence.append(evidence)
        next_review.revision = expected_review_revision + 1
        next_review.updated_at = datetime.now(UTC)
        event = AuditEvent(
            review_id=review.id,
            action="attach_evidence",
            actor=normalized_actor,
            payload={
                "evidence_id": evidence.id,
                "obligation_ids": selected_ids,
                "policy_id": policy_id,
                "authority": authority,
                "provenance": normalized_provenance,
            },
        )
        try:
            self.database.apply_transition(
                project=project,
                review=next_review,
                event=event,
                expected_project_version=expected_project_version,
                expected_review_revision=expected_review_revision,
            )
        except ConcurrentTransitionError as exc:
            raise DecisionBlocked(str(exc)) from exc
        return next_review

    def attach_dsse_attestation(
        self,
        review_id: str,
        *,
        obligation_ids: list[str],
        envelope: dict,
    ) -> ReviewPackage:
        review = self.database.get_review(review_id)
        project = self.database.get_project(review.project_id)
        expected_project_version = project.version
        expected_review_revision = review.revision
        if review.status != "open":
            raise DecisionBlocked(f"cannot attach evidence to a review in {review.status} status")
        selected_ids = list(dict.fromkeys(item.strip() for item in obligation_ids if item.strip()))
        if not selected_ids:
            raise DecisionBlocked("at least one evidence obligation must be selected")
        obligation_by_id = {item.id: item for item in review.evidence_obligations}
        if any(item not in obligation_by_id for item in selected_ids):
            raise DecisionBlocked("attestation contains an unknown obligation")
        obligations = [obligation_by_id[item] for item in selected_ids]
        if any(item.verification != "dsse_ed25519" for item in obligations):
            raise DecisionBlocked("selected obligation does not accept DSSE attestation evidence")
        now = datetime.now(UTC)
        active_roots = [
            root
            for root in project.attestation_trust_roots
            if root.accepts_new_attestations(now)
        ]
        if not active_roots:
            raise DecisionBlocked("project has no active attestation trust root")
        required_verifiers = {item.required_verifier_id for item in obligations}
        if len(required_verifiers) != 1:
            raise DecisionBlocked("selected obligations require different attestation verifiers")
        try:
            verified = verify_dsse_vsa(
                envelope,
                trust_roots=active_roots,
                expected_git_commit=review.target_ref,
                required_verifier_id=next(iter(required_verifiers)),
            )
        except AttestationVerificationError as exc:
            raise DecisionBlocked(str(exc)) from exc
        if verified.authority not in review.required_authorities:
            raise DecisionBlocked(
                f"attestation authority {verified.authority} is not valid for this proposal"
            )
        if any(
            item.details.get("envelope_sha256") == verified.envelope_sha256
            for item in review.evidence
        ):
            raise DecisionBlocked("this DSSE attestation is already attached to the review")
        missing_levels = [
            item.required_verified_level
            for item in obligations
            if item.required_verified_level not in verified.verified_levels
        ]
        if missing_levels:
            raise DecisionBlocked(f"VSA does not include required level {missing_levels[0]}")
        provenance = f"dsse-ed25519:{verified.key_id}:{verified.envelope_sha256}"
        mismatched_prefix = next(
            (
                item.required_provenance_prefix
                for item in obligations
                if item.required_provenance_prefix
                and not provenance.startswith(item.required_provenance_prefix)
            ),
            None,
        )
        if mismatched_prefix:
            raise DecisionBlocked(f"evidence provenance must start with {mismatched_prefix}")
        claim_ids = list(dict.fromkeys(item.claim_id for item in obligations))
        evidence = Evidence(
            kind="attestation",
            status="pass",
            outcome="supports",
            summary=(
                f"{verified.verifier_id} reported PASSED for {', '.join(verified.verified_levels)}"
            ),
            claim_ids=claim_ids,
            obligation_ids=selected_ids,
            artifact_ref=review.target_ref,
            provenance=provenance,
            recorded_by=verified.verifier_id,
            authority=verified.authority,
            policy_id=review.governing_policy,
            freshness="current",
            details={
                "signature_verified": True,
                "signature_algorithm": "ed25519",
                "key_id": verified.key_id,
                "payload_type": verified.payload_type,
                "predicate_type": verified.predicate_type,
                "verifier_id": verified.verifier_id,
                "resource_uri": verified.resource_uri,
                "subject_git_commit": verified.subject_git_commit,
                "verification_result": verified.verification_result,
                "verified_levels": verified.verified_levels,
                "envelope_sha256": verified.envelope_sha256,
                "dsse_envelope": deepcopy(envelope),
            },
        )
        next_review = review.model_copy(deep=True)
        next_review.evidence.append(evidence)
        next_review.revision = expected_review_revision + 1
        next_review.updated_at = datetime.now(UTC)
        event = AuditEvent(
            review_id=review.id,
            action="attach_dsse_attestation",
            actor=verified.verifier_id,
            payload={
                "evidence_id": evidence.id,
                "obligation_ids": selected_ids,
                "key_id": verified.key_id,
                "verifier_id": verified.verifier_id,
                "envelope_sha256": verified.envelope_sha256,
            },
        )
        try:
            self.database.apply_transition(
                project=project,
                review=next_review,
                event=event,
                expected_project_version=expected_project_version,
                expected_review_revision=expected_review_revision,
            )
        except ConcurrentTransitionError as exc:
            raise DecisionBlocked(str(exc)) from exc
        return next_review

    @staticmethod
    def _required_authorities(project: Project, deltas: list[ClaimDelta]) -> list[str]:
        claim_by_id = {claim.id: claim for claim in project.claims}
        values = [
            claim_by_id[delta.claim_id].authority.strip()
            for delta in deltas
            if delta.claim_id in claim_by_id and claim_by_id[delta.claim_id].authority.strip()
        ]
        values = list(dict.fromkeys(values))
        return values or [project.default_authority]

    @staticmethod
    def _authorize_governed_action(
        project: Project,
        review: ReviewPackage,
        *,
        actor: str,
        authority: str | None,
        policy_id: str | None,
        action: str,
    ) -> tuple[str, str, str]:
        if not project.authority_grants:
            normalized_authority = authority or project.default_authority
            normalized_policy = policy_id or project.policy_id
            if normalized_policy != project.policy_id:
                raise DecisionBlocked(f"decision must use governing policy {project.policy_id}")
            if normalized_authority not in review.required_authorities:
                raise DecisionBlocked("asserted authority is not valid for this proposal")
            return normalized_authority, normalized_policy, "local_single_user_policy"

        if policy_id != project.policy_id:
            raise DecisionBlocked(f"decision must use governing policy {project.policy_id}")
        if not authority or authority not in review.required_authorities:
            raise DecisionBlocked("asserted authority is not valid for this proposal")
        normalized_actor = actor.strip().casefold()
        grant = next(
            (
                item
                for item in project.authority_grants
                if item.authority == authority
                and action in item.actions
                and normalized_actor in {candidate.strip().casefold() for candidate in item.actors}
            ),
            None,
        )
        if grant is None:
            raise DecisionBlocked(
                f"actor {actor.strip()} is not authorized as {authority} for {action}"
            )
        return authority, policy_id, "project_authority_grant"

    @staticmethod
    def _authorize_decision(
        project: Project, review: ReviewPackage, action: DecisionAction
    ) -> tuple[DecisionAction, str]:
        authority, policy_id, provenance = ReviewService._authorize_governed_action(
            project,
            review,
            actor=action.actor,
            authority=action.authority,
            policy_id=action.policy_id,
            action=action.action,
        )
        normalized = action.model_copy(
            update={"authority": authority, "policy_id": policy_id}
        )
        if provenance == "local_single_user_policy":
            return normalized, provenance
        if not normalized.reason or len(normalized.reason.strip()) < 8:
            raise DecisionBlocked("a substantive decision rationale is required")
        return normalized, provenance

    def get_diff(self, review_id: str, max_chars: int = 60_000) -> dict[str, str | int | bool]:
        review = self.database.get_review(review_id)
        project = self.database.get_project(review.project_id)
        repository = GitRepository(project.repo_path)
        value = repository.diff(review.base_ref, review.target_ref, max_chars=max_chars + 1)
        truncated = len(value) > max_chars
        return {
            "review_id": review.id,
            "diff": value[:max_chars],
            "truncated": truncated,
            "character_count": len(value[:max_chars]),
        }

    @staticmethod
    def _deterministic_summary(findings, evidence, status: str = "open") -> str:
        open_critical = sum(1 for item in findings if item.severity == "critical" and item.status == "open")
        tests = next((item for item in evidence if item.kind == "tests"), None)
        test_text = tests.status if tests else "missing"
        test_clause = _test_clause(test_text)
        if status == "committed":
            return f"Committed to the governed project-state ledger. {test_clause.capitalize()}; no critical findings remain open."
        if status == "rejected":
            return "Rejected by the responsible human. Evidence is retained for audit."
        if status == "rebase_required":
            return "Rebase required before this proposal can advance against the current project state."
        if open_critical:
            finding_text = _count_phrase(open_critical, "open critical finding")
            return f"Decision required: {test_clause}; {finding_text} {'remains' if open_critical == 1 else 'remain'}."
        return f"No open critical findings. {test_clause.capitalize()}. Verify the evidence before committing."

    def decide(self, review_id: str, action: DecisionAction) -> ReviewPackage:
        review = self.database.get_review(review_id)
        project = self.database.get_project(review.project_id)
        expected_project_version = project.version
        expected_review_revision = review.revision
        review.current_project_version = project.version
        action, authority_provenance = self._authorize_decision(project, review, action)
        waiver_ids_before = {item.id for item in review.waivers}
        result = decide(review, action)
        commitments.apply_decision(project, review, action.action)
        waiver_ids = [item.id for item in result.review.waivers if item.id not in waiver_ids_before]
        decision_record = DecisionRecord(
            action=action.action,
            actor=action.actor.strip(),
            authority=action.authority or project.default_authority,
            policy_id=action.policy_id or project.policy_id,
            reason=action.reason,
            waiver_ids=waiver_ids,
            provenance=authority_provenance,
        )
        result.review.decision_records.append(decision_record)
        result.review.revision = expected_review_revision + 1
        result.event.payload.update(
            {
                "decision_record_id": decision_record.id,
                "policy_id": decision_record.policy_id,
                "authority": decision_record.authority,
                "authority_provenance": decision_record.provenance,
            }
        )
        if action.action == "rollback":
            result.review.evidence.append(
                Evidence(
                    kind="policy",
                    status="unknown",
                    outcome="inconclusive",
                    summary="Prior evidence is historical after rollback and does not validate the compensating state",
                    artifact_ref=result.review.base_ref,
                    provenance="rollback_invalidation",
                    freshness="stale",
                    invalidated_reason="The artifact version validated by this evidence was rolled back",
                )
            )
            result.review.summary = "Rolled back. Earlier evidence is retained for audit but no longer validates the current project state."
        else:
            result.review.summary = self._deterministic_summary(
                result.review.findings, result.review.evidence, result.review.status
            )
        if result.new_project_version is not None:
            project.version = result.new_project_version
            result.review.current_project_version = result.new_project_version
            if action.action == "commit":
                project.head_ref = result.review.target_ref
            elif action.action == "rollback":
                project.head_ref = result.review.base_ref
        try:
            self.database.apply_transition(
                project=project,
                review=result.review,
                event=result.event,
                expected_project_version=expected_project_version,
                expected_review_revision=expected_review_revision,
            )
        except ConcurrentTransitionError as exc:
            raise DecisionBlocked(str(exc)) from exc
        return result.review
