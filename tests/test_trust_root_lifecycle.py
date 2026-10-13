from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest
from fastapi.testclient import TestClient

from system.domain.models import AttestationTrustRoot, StructuralClaim
from system.domain.transitions import DecisionBlocked
from system.main import build_parser, main
from system.services.attestation import pae
from system.services.database import Database, database_runtime_lock
from system.services.review_service import ReviewService
from system.web.app import create_app as create_secure_app
from tests.helpers import create_alternate_target, create_capability_repo


VSA_TYPE = "https://slsa.dev/verification_summary/v1"
VERIFIER_ID = "https://ci.example.test/verifiers/source-policy/v1"
RESOURCE_PREFIX = "git+https://example.test/acme/capability@"
TRUST_ROOT_POSSESSION_POLICY_URI = (
    "https://agentic-consensus.local/policies/trust-root-possession/v1"
)
TRUST_ROOT_POSSESSION_LEVEL = "CONSENSUS_TRUST_ROOT_POSSESSION_V1"


def create_app(database_path: Path):
    return create_secure_app(database_path, require_authentication=False)


def trust_root(private_key: Ed25519PrivateKey, key_id: str) -> AttestationTrustRoot:
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return AttestationTrustRoot(
        key_id=key_id,
        public_key_base64=base64.b64encode(public_bytes).decode(),
        verifier_id=VERIFIER_ID,
        authority="security owner",
        resource_uri_prefix=RESOURCE_PREFIX,
        predicate_types=[VSA_TYPE],
    )


def signed_proof(
    private_key: Ed25519PrivateKey,
    key_id: str,
    target_ref: str,
    *,
    policy_uri: str = "https://example.test/policies/source-verification/v1",
    verified_levels: list[str] | None = None,
) -> dict:
    statement = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [{"name": "source revision", "digest": {"gitCommit": target_ref}}],
        "predicateType": VSA_TYPE,
        "predicate": {
            "verifier": {"id": VERIFIER_ID},
            "resourceUri": f"{RESOURCE_PREFIX}{target_ref}",
            "policy": {"uri": policy_uri},
            "verificationResult": "PASSED",
            "verifiedLevels": verified_levels or ["SLSA_SOURCE_LEVEL_2"],
            "slsaVersion": "1.2",
        },
    }
    payload_type = "application/vnd.in-toto+json"
    payload = json.dumps(statement, separators=(",", ":"), sort_keys=True).encode()
    signature = private_key.sign(pae(payload_type.encode(), payload))
    return {
        "payloadType": payload_type,
        "payload": base64.b64encode(payload).decode(),
        "signatures": [{"keyid": key_id, "sig": base64.b64encode(signature).decode()}],
    }


def signed_possession_proof(
    private_key: Ed25519PrivateKey, key_id: str, target_ref: str
) -> dict:
    return signed_proof(
        private_key,
        key_id,
        target_ref,
        policy_uri=TRUST_ROOT_POSSESSION_POLICY_URI,
        verified_levels=[TRUST_ROOT_POSSESSION_LEVEL],
    )


def signed_claim() -> StructuralClaim:
    return StructuralClaim(
        id="authority.task_scoped_only",
        title="Connectors use task-scoped capabilities",
        forbidden_modules=["legacy.workspace_credentials"],
        authority="security owner",
        evidence_obligations=[
            {
                "label": "signed source-policy verification",
                "verification": "dsse_ed25519",
                "required_verifier_id": VERIFIER_ID,
                "required_verified_level": "SLSA_SOURCE_LEVEL_2",
            }
        ],
    )


def test_adds_a_proven_trust_root_as_a_versioned_project_transition(tmp_path: Path):
    repo, base, _ = create_capability_repo(tmp_path)
    database = Database(tmp_path / "control.db")
    service = ReviewService(database)
    project = service.create_project(
        name="Capability migration",
        repo_path=repo,
        head_ref=base,
        test_command=[],
        claims=[],
        policy_id="security-change-control/v1",
        default_authority="security owner",
    )
    private_key = Ed25519PrivateKey.generate()
    root = trust_root(private_key, "ci-source-ed25519-2027")

    updated = service.change_trust_roots(
        project.id,
        action="add",
        actor="security-lead@example.test",
        authority="security owner",
        policy_id=project.policy_id,
        reason="Add the rotated CI source verification key",
        expected_project_version=project.version,
        new_root=root,
        new_key_proof=signed_possession_proof(private_key, root.key_id, project.head_ref),
    )

    assert updated.version == project.version + 1
    assert len(updated.attestation_trust_roots) == 1
    added = updated.attestation_trust_roots[0]
    assert added.status == "active"
    assert added.added_by == "security-lead@example.test"
    assert added.added_under_policy == project.policy_id
    assert database.get_project(project.id) == updated
    events = database.list_project_events(project.id)
    assert len(events) == 1
    assert events[0].action == "trust_root_add"
    assert events[0].project_version == updated.version
    assert events[0].payload["key_id"] == root.key_id
    assert events[0].payload["proof_envelope_sha256"]


def test_builds_a_machine_signable_possession_template_that_the_service_accepts(
    tmp_path: Path,
):
    repo, base, _ = create_capability_repo(tmp_path)
    database = Database(tmp_path / "proof-template.db")
    service = ReviewService(database)
    project = service.create_project(
        name="Capability migration",
        repo_path=repo,
        head_ref=base,
        test_command=[],
        claims=[],
        policy_id="security-change-control/v1",
        default_authority="security owner",
    )
    private_key = Ed25519PrivateKey.generate()
    root = trust_root(private_key, "ci-source-ed25519-2027")

    template = service.build_trust_root_possession_template(project.id, new_root=root)

    assert template["contract"] == {
        "algorithm": "ed25519",
        "key_id": root.key_id,
        "public_key_base64": root.public_key_base64,
        "project_head": project.head_ref,
        "project_version": project.version,
        "verifier_id": root.verifier_id,
        "resource_uri": f"{RESOURCE_PREFIX}{project.head_ref}",
        "policy_uri": TRUST_ROOT_POSSESSION_POLICY_URI,
        "required_verified_level": TRUST_ROOT_POSSESSION_LEVEL,
    }
    envelope = template["envelope"]
    payload = base64.b64decode(envelope["payload"], validate=True)
    statement = json.loads(payload)
    assert statement["subject"][0]["digest"]["gitCommit"] == project.head_ref
    assert statement["predicate"]["policy"]["uri"] == TRUST_ROOT_POSSESSION_POLICY_URI
    assert statement["predicate"]["verifiedLevels"] == [TRUST_ROOT_POSSESSION_LEVEL]
    signing_input = base64.b64decode(template["signing_input_base64"], validate=True)
    assert signing_input == pae(envelope["payloadType"].encode(), payload)
    envelope["signatures"][0]["sig"] = base64.b64encode(
        private_key.sign(signing_input)
    ).decode()

    updated = service.change_trust_roots(
        project.id,
        action="add",
        actor="security-lead@example.test",
        authority="security owner",
        policy_id=project.policy_id,
        reason="Add the rotated CI source verification key",
        expected_project_version=project.version,
        new_root=root,
        new_key_proof=envelope,
    )

    assert updated.attestation_trust_roots[0].key_id == root.key_id


@pytest.mark.parametrize(
    ("policy_uri", "verified_levels"),
    [
        (TRUST_ROOT_POSSESSION_POLICY_URI, ["SLSA_SOURCE_LEVEL_2"]),
        (
            "https://example.test/policies/source-verification/v1",
            [TRUST_ROOT_POSSESSION_LEVEL],
        ),
    ],
)
def test_new_key_possession_proof_requires_its_dedicated_policy_and_level(
    tmp_path: Path, policy_uri: str, verified_levels: list[str]
):
    repo, base, _ = create_capability_repo(tmp_path)
    database = Database(tmp_path / "proof-purpose.db")
    service = ReviewService(database)
    project = service.create_project(
        name="Capability migration",
        repo_path=repo,
        head_ref=base,
        test_command=[],
        claims=[],
        policy_id="security-change-control/v1",
        default_authority="security owner",
    )
    private_key = Ed25519PrivateKey.generate()
    root = trust_root(private_key, "ci-source-ed25519-2027")

    with pytest.raises(DecisionBlocked, match="possession proof"):
        service.change_trust_roots(
            project.id,
            action="add",
            actor="security-lead@example.test",
            authority="security owner",
            policy_id=project.policy_id,
            reason="Add the rotated CI source verification key",
            expected_project_version=project.version,
            new_root=root,
            new_key_proof=signed_proof(
                private_key,
                root.key_id,
                project.head_ref,
                policy_uri=policy_uri,
                verified_levels=verified_levels,
            ),
        )

    assert database.get_project(project.id).attestation_trust_roots == []
    assert database.list_project_events(project.id) == []


def test_trust_changes_require_an_explicit_manage_trust_grant(tmp_path: Path):
    repo, base, _ = create_capability_repo(tmp_path)
    database = Database(tmp_path / "authorized.db")
    service = ReviewService(database)
    project = service.create_project(
        name="Capability migration",
        repo_path=repo,
        head_ref=base,
        test_command=[],
        claims=[],
        policy_id="security-change-control/v1",
        default_authority="security owner",
        authority_grants=[
            {
                "authority": "security owner",
                "actors": ["security-lead@example.test"],
                "actions": ["manage_trust"],
            }
        ],
    )
    private_key = Ed25519PrivateKey.generate()
    root = trust_root(private_key, "ci-source-ed25519-2027")
    request = {
        "action": "add",
        "authority": "security owner",
        "policy_id": project.policy_id,
        "reason": "Add the rotated CI source verification key",
        "expected_project_version": project.version,
        "new_root": root,
        "new_key_proof": signed_possession_proof(private_key, root.key_id, project.head_ref),
    }

    with pytest.raises(DecisionBlocked, match="not authorized"):
        service.change_trust_roots(
            project.id,
            actor="untrusted@example.test",
            **request,
        )

    updated = service.change_trust_roots(
        project.id,
        actor="security-lead@example.test",
        **request,
    )
    assert updated.attestation_trust_roots[0].added_by == "security-lead@example.test"


def test_existing_decision_owner_can_receive_an_audited_trust_admin_upgrade(tmp_path: Path):
    repo, base, _ = create_capability_repo(tmp_path)
    database = Database(tmp_path / "trust-admin-upgrade.db")
    service = ReviewService(database)
    project = service.create_project(
        name="Capability migration",
        repo_path=repo,
        head_ref=base,
        test_command=[],
        claims=[],
        policy_id="security-change-control/v1",
        default_authority="security owner",
        authority_grants=[
            {
                "authority": "security owner",
                "actors": ["security-lead@example.test"],
                "actions": ["commit", "waive", "rebase", "reject", "rollback", "attest"],
            }
        ],
    )

    with pytest.raises(DecisionBlocked, match="existing commit authority"):
        service.grant_trust_administrator(
            project.id,
            actor="untrusted@example.test",
            reason="Authorize trust lifecycle management after the version upgrade",
            expected_project_version=project.version,
        )

    updated = service.grant_trust_administrator(
        project.id,
        actor="security-lead@example.test",
        reason="Authorize trust lifecycle management after the version upgrade",
        expected_project_version=project.version,
    )

    assert updated.version == project.version + 1
    assert "manage_trust" in updated.authority_grants[0].actions
    event = database.list_project_events(project.id)[0]
    assert event.action == "authority_grant_extend"
    assert event.payload == {
        "actor": "security-lead@example.test",
        "authority": "security owner",
        "granted_action": "manage_trust",
    }


def test_cli_applies_the_offline_trust_admin_upgrade(tmp_path: Path, capsys):
    repo, base, _ = create_capability_repo(tmp_path)
    database_path = tmp_path / "trust-admin-cli.db"
    database = Database(database_path)
    project = ReviewService(database).create_project(
        name="Capability migration",
        repo_path=repo,
        head_ref=base,
        test_command=[],
        claims=[],
        policy_id="security-change-control/v1",
        default_authority="security owner",
        authority_grants=[
            {
                "authority": "security owner",
                "actors": ["security-lead@example.test"],
                "actions": ["commit", "waive", "rebase", "reject", "rollback", "attest"],
            }
        ],
    )

    exit_code = main(
        [
            "--database",
            str(database_path),
            "grant-trust-admin",
            "--project",
            project.id,
            "--actor",
            "security-lead@example.test",
            "--reason",
            "Authorize trust lifecycle management after the version upgrade",
            "--expected-version",
            str(project.version),
        ]
    )

    assert exit_code == 0
    assert '"granted_action": "manage_trust"' in capsys.readouterr().out
    assert "manage_trust" in database.get_project(project.id).authority_grants[0].actions


def test_offline_trust_admin_upgrade_refuses_a_live_console(tmp_path: Path, capsys):
    repo, base, _ = create_capability_repo(tmp_path)
    database_path = tmp_path / "trust-admin-locked.db"
    database = Database(database_path)
    project = ReviewService(database).create_project(
        name="Capability migration",
        repo_path=repo,
        head_ref=base,
        test_command=[],
        claims=[],
        policy_id="security-change-control/v1",
        default_authority="security owner",
        authority_grants=[
            {
                "authority": "security owner",
                "actors": ["security-lead@example.test"],
                "actions": ["commit", "waive", "rebase", "reject", "rollback", "attest"],
            }
        ],
    )
    command = [
        "--database",
        str(database_path),
        "grant-trust-admin",
        "--project",
        project.id,
        "--actor",
        "security-lead@example.test",
        "--reason",
        "Authorize trust lifecycle management after the version upgrade",
        "--expected-version",
        str(project.version),
    ]

    with database_runtime_lock(database_path):
        assert main(command) == 2

    assert "still in use" in capsys.readouterr().err
    assert "manage_trust" not in database.get_project(project.id).authority_grants[0].actions


def test_cli_help_exposes_the_offline_trust_proof_signer():
    help_text = build_parser().format_help()

    assert "sign-trust-proof" in help_text
    assert "offline" in help_text


def test_prospective_revocation_preserves_prior_evidence_but_blocks_new_imports(tmp_path: Path):
    repo, base, target = create_capability_repo(tmp_path)
    private_key = Ed25519PrivateKey.generate()
    root = trust_root(private_key, "ci-source-ed25519-2026")
    database = Database(tmp_path / "revoke.db")
    service = ReviewService(database)
    project = service.create_project(
        name="Capability migration",
        repo_path=repo,
        head_ref=base,
        test_command=[],
        claims=[signed_claim()],
        policy_id="security-change-control/v1",
        default_authority="security owner",
        attestation_trust_roots=[root],
    )
    review = service.create_review(project.id, base_ref=base, target_ref=target)
    obligation_id = review.evidence_obligations[0].id
    service.attach_dsse_attestation(
        review.id,
        obligation_ids=[obligation_id],
        envelope=signed_proof(private_key, root.key_id, target),
    )

    updated = service.change_trust_roots(
        project.id,
        action="revoke",
        actor="security-lead@example.test",
        authority="security owner",
        policy_id=project.policy_id,
        reason="Retire the superseded source verification key",
        expected_project_version=project.version,
        key_id=root.key_id,
        revocation_mode="prospective",
    )

    revoked = updated.attestation_trust_roots[0]
    assert updated.version == project.version + 1
    assert revoked.status == "revoked"
    assert revoked.revocation_mode == "prospective"
    assert revoked.revoked_by == "security-lead@example.test"
    assert revoked.revocation_reason == "Retire the superseded source verification key"
    assert service.get_change_package(review.id).obligation_statuses[0].status == "satisfied"
    assert database.list_project_events(project.id)[-1].action == "trust_root_revoke"

    alternate = create_alternate_target(
        repo,
        base,
        path="connector_registry.py",
        content=(
            "from legacy.workspace_credentials import TOKEN\n"
            "PROVIDERS = {'calendar': 'security.task_scope', 'archive': TOKEN}\n"
        ),
        message="alternate capability migration",
    )
    new_review = service.create_review(project.id, base_ref=base, target_ref=alternate)
    with pytest.raises(DecisionBlocked, match="active attestation trust root"):
        service.attach_dsse_attestation(
            new_review.id,
            obligation_ids=[new_review.evidence_obligations[0].id],
            envelope=signed_proof(private_key, root.key_id, alternate),
        )


def test_retroactive_revocation_marks_previously_accepted_evidence_stale(tmp_path: Path):
    repo, base, target = create_capability_repo(tmp_path)
    private_key = Ed25519PrivateKey.generate()
    root = trust_root(private_key, "compromised-ci-key")
    database = Database(tmp_path / "retroactive.db")
    service = ReviewService(database)
    project = service.create_project(
        name="Capability migration",
        repo_path=repo,
        head_ref=base,
        test_command=[],
        claims=[signed_claim()],
        policy_id="security-change-control/v1",
        default_authority="security owner",
        attestation_trust_roots=[root],
    )
    review = service.create_review(project.id, base_ref=base, target_ref=target)
    service.attach_dsse_attestation(
        review.id,
        obligation_ids=[review.evidence_obligations[0].id],
        envelope=signed_proof(private_key, root.key_id, target),
    )

    service.change_trust_roots(
        project.id,
        action="revoke",
        actor="security-lead@example.test",
        authority="security owner",
        policy_id=project.policy_id,
        reason="Invalidate evidence signed by the compromised CI key",
        expected_project_version=project.version,
        key_id=root.key_id,
        revocation_mode="retroactive",
        confirm_retroactive=True,
    )

    manifest = service.get_change_package(review.id)
    assert manifest.obligation_statuses[0].status == "stale"
    obligation_check = next(
        item for item in manifest.admission_checks if item.key == "evidence_obligations"
    )
    assert obligation_check.status == "block"
    freshness_check = next(
        item for item in manifest.admission_checks if item.key == "evidence_freshness"
    )
    assert freshness_check.status == "warn"
    assert "revoked trust root" in freshness_check.summary
    attached_ids = [
        item.id for item in database.get_review(review.id).evidence
        if item.details.get("key_id") == root.key_id
    ]
    assert getattr(manifest, "invalidated_evidence_ids", None) == attached_ids


def test_retroactive_revocation_requires_explicit_confirmation(tmp_path: Path):
    repo, base, _ = create_capability_repo(tmp_path)
    private_key = Ed25519PrivateKey.generate()
    root = trust_root(private_key, "compromised-ci-key")
    database = Database(tmp_path / "retroactive-confirmation.db")
    service = ReviewService(database)
    project = service.create_project(
        name="Capability migration",
        repo_path=repo,
        head_ref=base,
        test_command=[],
        claims=[],
        policy_id="security-change-control/v1",
        default_authority="security owner",
        attestation_trust_roots=[root],
    )

    with pytest.raises(DecisionBlocked, match="explicit confirmation"):
        service.change_trust_roots(
            project.id,
            action="revoke",
            actor="security-lead@example.test",
            authority="security owner",
            policy_id=project.policy_id,
            reason="Invalidate all evidence signed by the compromised CI key",
            expected_project_version=project.version,
            key_id=root.key_id,
            revocation_mode="retroactive",
        )

    stored = database.get_project(project.id)
    assert stored.version == project.version
    assert stored.attestation_trust_roots[0].status == "active"
    assert database.list_project_events(project.id) == []


def test_rotation_revokes_the_old_root_and_adds_a_proven_replacement_atomically(tmp_path: Path):
    repo, base, target = create_capability_repo(tmp_path)
    old_private_key = Ed25519PrivateKey.generate()
    new_private_key = Ed25519PrivateKey.generate()
    old_root = trust_root(old_private_key, "ci-source-ed25519-2026")
    new_root = trust_root(new_private_key, "ci-source-ed25519-2027")
    database = Database(tmp_path / "rotate.db")
    service = ReviewService(database)
    project = service.create_project(
        name="Capability migration",
        repo_path=repo,
        head_ref=base,
        test_command=[],
        claims=[signed_claim()],
        policy_id="security-change-control/v1",
        default_authority="security owner",
        attestation_trust_roots=[old_root],
    )

    updated = service.change_trust_roots(
        project.id,
        action="rotate",
        actor="security-lead@example.test",
        authority="security owner",
        policy_id=project.policy_id,
        reason="Rotate the CI signing key before its scheduled retirement",
        expected_project_version=project.version,
        key_id=old_root.key_id,
        new_root=new_root,
        new_key_proof=signed_possession_proof(
            new_private_key, new_root.key_id, project.head_ref
        ),
        revocation_mode="prospective",
    )

    assert updated.version == project.version + 1
    assert [(item.key_id, item.status) for item in updated.attestation_trust_roots] == [
        (old_root.key_id, "revoked"),
        (new_root.key_id, "active"),
    ]
    events = database.list_project_events(project.id)
    assert len(events) == 1
    assert events[0].action == "trust_root_rotate"
    assert events[0].payload["old_key_id"] == old_root.key_id
    assert events[0].payload["new_key_id"] == new_root.key_id
    assert events[0].payload["proof_envelope_sha256"]

    review = service.create_review(project.id, base_ref=base, target_ref=target)
    obligation_id = review.evidence_obligations[0].id
    with pytest.raises(DecisionBlocked, match="no valid signature"):
        service.attach_dsse_attestation(
            review.id,
            obligation_ids=[obligation_id],
            envelope=signed_proof(old_private_key, old_root.key_id, target),
        )
    accepted = service.attach_dsse_attestation(
        review.id,
        obligation_ids=[obligation_id],
        envelope=signed_proof(new_private_key, new_root.key_id, target),
    )
    assert accepted.evidence[-1].details["key_id"] == new_root.key_id

    with pytest.raises(DecisionBlocked, match="stale project state"):
        service.change_trust_roots(
            project.id,
            action="rotate",
            actor="security-lead@example.test",
            authority="security owner",
            policy_id=project.policy_id,
            reason="Repeat a stale rotation request",
            expected_project_version=project.version,
            key_id=old_root.key_id,
            new_root=new_root,
            new_key_proof=signed_possession_proof(
                new_private_key, new_root.key_id, project.head_ref
            ),
        )


@pytest.mark.parametrize("window", ["future", "expired"])
def test_add_rejects_a_key_outside_its_declared_validity_window(
    tmp_path: Path, window: str
):
    repo, base, _ = create_capability_repo(tmp_path)
    private_key = Ed25519PrivateKey.generate()
    root = trust_root(private_key, f"{window}-ci-key")
    now = datetime.now(UTC)
    if window == "future":
        valid_from, valid_until = now + timedelta(days=1), None
    else:
        valid_from, valid_until = now - timedelta(days=2), now - timedelta(days=1)
    root = AttestationTrustRoot.model_validate(
        {
            **root.model_dump(mode="python"),
            "valid_from": valid_from,
            "valid_until": valid_until,
        }
    )
    database = Database(tmp_path / f"{window}.db")
    service = ReviewService(database)
    project = service.create_project(
        name="Capability migration",
        repo_path=repo,
        head_ref=base,
        test_command=[],
        claims=[],
        policy_id="security-change-control/v1",
        default_authority="security owner",
    )

    with pytest.raises(DecisionBlocked, match="not currently valid"):
        service.change_trust_roots(
            project.id,
            action="add",
            actor="security-lead@example.test",
            authority="security owner",
            policy_id=project.policy_id,
            reason="Attempt to add a key outside its validity window",
            expected_project_version=project.version,
            new_root=root,
            new_key_proof=signed_possession_proof(
                private_key, root.key_id, project.head_ref
            ),
        )

    assert database.get_project(project.id).version == project.version
    assert database.list_project_events(project.id) == []


def test_can_revoke_a_scheduled_root_before_its_validity_window(tmp_path: Path):
    repo, base, _ = create_capability_repo(tmp_path)
    private_key = Ed25519PrivateKey.generate()
    root = trust_root(private_key, "scheduled-ci-key")
    valid_from = datetime.now(UTC) + timedelta(days=2)
    root = AttestationTrustRoot.model_validate(
        {
            **root.model_dump(mode="python"),
            "valid_from": valid_from,
            "valid_until": None,
        }
    )
    database = Database(tmp_path / "scheduled-revoke.db")
    service = ReviewService(database)
    project = service.create_project(
        name="Capability migration",
        repo_path=repo,
        head_ref=base,
        test_command=[],
        claims=[],
        policy_id="security-change-control/v1",
        default_authority="security owner",
        attestation_trust_roots=[root],
    )

    updated = service.change_trust_roots(
        project.id,
        action="revoke",
        actor="security-lead@example.test",
        authority="security owner",
        policy_id=project.policy_id,
        reason="Cancel this scheduled key before it becomes trusted",
        expected_project_version=project.version,
        key_id=root.key_id,
        revocation_mode="prospective",
    )

    revoked = updated.attestation_trust_roots[0]
    assert revoked.status == "revoked"
    assert revoked.revoked_at < revoked.valid_from
    assert revoked.valid_until is None
    assert database.list_project_events(project.id)[0].action == "trust_root_revoke"


def test_api_exposes_trust_changes_and_the_project_audit_timeline(tmp_path: Path):
    repo, base, _ = create_capability_repo(tmp_path)
    private_key = Ed25519PrivateKey.generate()
    root = trust_root(private_key, "api-ci-key-2027")
    with TestClient(create_app(tmp_path / "api.db")) as client:
        project_response = client.post(
            "/api/projects",
            json={
                "name": "Capability migration",
                "repo_path": str(repo),
                "head_ref": base,
                "test_command": [],
                "claims": [],
                "policy_id": "security-change-control/v1",
                "default_authority": "security owner",
            },
        )
        assert project_response.status_code == 201
        project = project_response.json()

        changed = client.post(
            f"/api/projects/{project['id']}/trust-roots/changes",
            json={
                "action": "add",
                "actor": "security-lead@example.test",
                "authority": "security owner",
                "policy_id": project["policy_id"],
                "reason": "Add the CI key through the governed API",
                "expected_project_version": project["version"],
                "new_root": root.model_dump(mode="json"),
                "new_key_proof": signed_possession_proof(
                    private_key, root.key_id, project["head_ref"]
                ),
            },
        )

        assert changed.status_code == 200
        assert changed.json()["version"] == project["version"] + 1
        events = client.get(f"/api/projects/{project['id']}/events")
        assert events.status_code == 200
        assert events.json()[0]["action"] == "trust_root_add"
        assert events.json()[0]["payload"]["key_id"] == root.key_id


def test_revoked_key_material_cannot_be_reintroduced_under_a_new_key_id(tmp_path: Path):
    repo, base, _ = create_capability_repo(tmp_path)
    private_key = Ed25519PrivateKey.generate()
    original_root = trust_root(private_key, "compromised-ci-key")
    database = Database(tmp_path / "key-alias.db")
    service = ReviewService(database)
    project = service.create_project(
        name="Capability migration",
        repo_path=repo,
        head_ref=base,
        test_command=[],
        claims=[],
        policy_id="security-change-control/v1",
        default_authority="security owner",
        attestation_trust_roots=[original_root],
    )
    revoked = service.change_trust_roots(
        project.id,
        action="revoke",
        actor="security-lead@example.test",
        authority="security owner",
        policy_id=project.policy_id,
        reason="Revoke key material exposed in a CI incident",
        expected_project_version=project.version,
        key_id=original_root.key_id,
        revocation_mode="retroactive",
        confirm_retroactive=True,
    )
    aliased_root = trust_root(private_key, "apparently-new-ci-key")

    with pytest.raises(DecisionBlocked, match="public key has already been used"):
        service.change_trust_roots(
            project.id,
            action="add",
            actor="security-lead@example.test",
            authority="security owner",
            policy_id=project.policy_id,
            reason="Attempt to reintroduce the same key under a new identifier",
            expected_project_version=revoked.version,
            new_root=aliased_root,
            new_key_proof=signed_possession_proof(
                private_key, aliased_root.key_id, project.head_ref
            ),
        )

    stored = database.get_project(project.id)
    assert stored.version == revoked.version
    assert len(stored.attestation_trust_roots) == 1


def test_project_registration_rejects_duplicate_public_key_aliases(tmp_path: Path):
    repo, base, _ = create_capability_repo(tmp_path)
    private_key = Ed25519PrivateKey.generate()
    first = trust_root(private_key, "ci-key-primary")
    alias = trust_root(private_key, "ci-key-alias")
    service = ReviewService(Database(tmp_path / "registration-alias.db"))

    with pytest.raises(ValueError, match="public keys must be unique"):
        service.create_project(
            name="Capability migration",
            repo_path=repo,
            head_ref=base,
            test_command=[],
            claims=[],
            policy_id="security-change-control/v1",
            default_authority="security owner",
            attestation_trust_roots=[first, alias],
        )
