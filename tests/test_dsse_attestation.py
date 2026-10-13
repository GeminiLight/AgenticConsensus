from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from system.domain.models import AttestationTrustRoot, StructuralClaim
from system.domain.transitions import DecisionBlocked, evidence_obligation_statuses
from system.services.attestation import AttestationVerificationError, pae, verify_dsse_vsa
from system.services.database import Database
from system.services.review_service import ReviewService
from system.web.app import create_app as create_secure_app
from tests.helpers import create_capability_repo


VSA_TYPE = "https://slsa.dev/verification_summary/v1"
VERIFIER_ID = "https://ci.example.test/verifiers/source-policy/v1"
RESOURCE_PREFIX = "git+https://example.test/acme/capability@"
KEY_ID = "ci-source-ed25519-2026"


def create_app(database_path: Path):
    return create_secure_app(database_path, require_authentication=False)


def public_key_base64(private_key: Ed25519PrivateKey) -> str:
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(public_bytes).decode()


def trust_root(
    private_key: Ed25519PrivateKey, *, authority: str = "security owner"
) -> AttestationTrustRoot:
    return AttestationTrustRoot(
        key_id=KEY_ID,
        algorithm="ed25519",
        public_key_base64=public_key_base64(private_key),
        verifier_id=VERIFIER_ID,
        authority=authority,
        resource_uri_prefix=RESOURCE_PREFIX,
        predicate_types=[VSA_TYPE],
    )


def statement(target_ref: str, *, result: str = "PASSED", level: str = "SLSA_SOURCE_LEVEL_2") -> dict:
    return {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [{"name": "source revision", "digest": {"gitCommit": target_ref}}],
        "predicateType": VSA_TYPE,
        "predicate": {
            "verifier": {"id": VERIFIER_ID, "version": {"policy-engine": "1.0"}},
            "resourceUri": f"{RESOURCE_PREFIX}{target_ref}",
            "policy": {"uri": "https://example.test/policies/source-change/v1"},
            "verificationResult": result,
            "verifiedLevels": [level],
            "slsaVersion": "1.2",
        },
    }


def signed_envelope(private_key: Ed25519PrivateKey, payload: dict) -> dict:
    payload_type = "application/vnd.in-toto+json"
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    signature = private_key.sign(pae(payload_type.encode(), payload_bytes))
    return {
        "payloadType": payload_type,
        "payload": base64.b64encode(payload_bytes).decode(),
        "signatures": [{"keyid": KEY_ID, "sig": base64.b64encode(signature).decode()}],
    }


def signed_raw_envelope(private_key: Ed25519PrivateKey, payload_bytes: bytes) -> dict:
    payload_type = "application/vnd.in-toto+json"
    signature = private_key.sign(pae(payload_type.encode(), payload_bytes))
    return {
        "payloadType": payload_type,
        "payload": base64.b64encode(payload_bytes).decode(),
        "signatures": [{"keyid": KEY_ID, "sig": base64.b64encode(signature).decode()}],
    }


def test_verifies_dsse_before_accepting_a_target_bound_vsa():
    private_key = Ed25519PrivateKey.generate()
    target_ref = "a" * 40

    verified = verify_dsse_vsa(
        signed_envelope(private_key, statement(target_ref)),
        trust_roots=[trust_root(private_key)],
        expected_git_commit=target_ref,
        required_verifier_id=VERIFIER_ID,
        required_verified_level="SLSA_SOURCE_LEVEL_2",
    )

    assert verified.key_id == KEY_ID
    assert verified.verifier_id == VERIFIER_ID
    assert verified.subject_git_commit == target_ref
    assert verified.predicate_type == VSA_TYPE
    assert verified.verification_result == "PASSED"
    assert verified.verified_levels == ["SLSA_SOURCE_LEVEL_2"]
    assert len(verified.envelope_sha256) == 64


@pytest.mark.parametrize("attack", ["tampered_payload", "wrong_target", "failed_result", "untrusted_key"])
def test_rejects_tampering_wrong_subject_failed_policy_and_untrusted_signers(attack: str):
    private_key = Ed25519PrivateKey.generate()
    target_ref = "b" * 40
    payload = statement(target_ref, result="FAILED" if attack == "failed_result" else "PASSED")
    if attack == "wrong_target":
        payload = statement("c" * 40)
    envelope = signed_envelope(private_key, payload)
    roots = [trust_root(private_key)]
    if attack == "tampered_payload":
        decoded = json.loads(base64.b64decode(envelope["payload"]))
        decoded["predicate"]["verificationResult"] = "FAILED"
        envelope["payload"] = base64.b64encode(
            json.dumps(decoded, separators=(",", ":"), sort_keys=True).encode()
        ).decode()
    if attack == "untrusted_key":
        roots = [trust_root(Ed25519PrivateKey.generate())]

    with pytest.raises(AttestationVerificationError):
        verify_dsse_vsa(
            envelope,
            trust_roots=roots,
            expected_git_commit=target_ref,
            required_verifier_id=VERIFIER_ID,
            required_verified_level="SLSA_SOURCE_LEVEL_2",
        )


def test_rejects_an_authentic_payload_with_duplicate_json_policy_fields():
    private_key = Ed25519PrivateKey.generate()
    target_ref = "d" * 40
    payload = json.dumps(statement(target_ref), separators=(",", ":"), sort_keys=True)
    payload = payload.replace(
        '"verificationResult":"PASSED"',
        '"verificationResult":"FAILED","verificationResult":"PASSED"',
    ).encode()

    with pytest.raises(AttestationVerificationError, match="duplicate JSON field"):
        verify_dsse_vsa(
            signed_raw_envelope(private_key, payload),
            trust_roots=[trust_root(private_key)],
            expected_git_commit=target_ref,
            required_verifier_id=VERIFIER_ID,
            required_verified_level="SLSA_SOURCE_LEVEL_2",
        )


def test_verified_dsse_evidence_satisfies_only_the_selected_signed_obligation(tmp_path: Path):
    repo, base, target = create_capability_repo(tmp_path)
    private_key = Ed25519PrivateKey.generate()
    database = Database(tmp_path / "control.db")
    service = ReviewService(database)
    project = service.create_project(
        name="Capability migration",
        repo_path=repo,
        repo_label="demo://capability-migration",
        head_ref=base,
        test_command=["python3", "-m", "unittest", "-q"],
        policy_id="security-change-control/v1",
        default_authority="security owner",
        authority_grants=[
            {
                "authority": "security owner",
                "actors": ["security-lead@example.test"],
                "actions": ["commit", "waive", "rebase", "reject", "rollback", "attest"],
            }
        ],
        attestation_trust_roots=[trust_root(private_key)],
        claims=[
            StructuralClaim(
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
                        "required_provenance_prefix": "dsse-ed25519:",
                    },
                    "human migration review",
                ],
            )
        ],
    )
    review = service.create_review(project.id, base_ref=base, target_ref=target)
    signed_obligation, human_obligation = review.evidence_obligations

    with pytest.raises(DecisionBlocked, match="verified DSSE"):
        service.attach_evidence(
            review.id,
            actor="security-lead@example.test",
            authority="security owner",
            policy_id=project.policy_id,
            obligation_ids=[signed_obligation.id],
            summary="Claims this came from CI",
            provenance="dsse-ed25519:not-actually-signed",
        )

    updated = service.attach_dsse_attestation(
        review.id,
        obligation_ids=[signed_obligation.id],
        envelope=signed_envelope(private_key, statement(target)),
    )

    statuses = {item.obligation_id: item.status for item in evidence_obligation_statuses(updated)}
    assert statuses == {signed_obligation.id: "satisfied", human_obligation.id: "missing"}
    evidence = updated.evidence[-1]
    assert evidence.recorded_by == VERIFIER_ID
    assert evidence.authority == "security owner"
    assert evidence.artifact_ref == target
    assert evidence.details["signature_verified"] is True
    assert evidence.details["key_id"] == KEY_ID
    assert evidence.details["dsse_envelope"] == signed_envelope(private_key, statement(target))
    assert database.list_events(review.id)[-1].action == "attach_dsse_attestation"


def test_api_rejects_tampered_dsse_then_admits_the_valid_envelope(tmp_path: Path):
    repo, base, target = create_capability_repo(tmp_path)
    private_key = Ed25519PrivateKey.generate()
    root = trust_root(private_key)
    with TestClient(create_app(tmp_path / "api.db")) as client:
        project = client.post(
            "/api/projects",
            json={
                "name": "Capability migration",
                "repo_path": str(repo),
                "repo_label": "demo://capability-migration",
                "head_ref": base,
                "test_command": ["python3", "-m", "unittest", "-q"],
                "policy_id": "security-change-control/v1",
                "default_authority": "security owner",
                "attestation_trust_roots": [root.model_dump(mode="json")],
                "claims": [
                    {
                        "id": "authority.task_scoped_only",
                        "title": "Connectors use task-scoped capabilities",
                        "forbidden_modules": ["legacy.workspace_credentials"],
                        "authority": "security owner",
                        "evidence_obligations": [
                            {
                                "label": "signed source-policy verification",
                                "verification": "dsse_ed25519",
                                "required_verifier_id": VERIFIER_ID,
                                "required_verified_level": "SLSA_SOURCE_LEVEL_2",
                            }
                        ],
                    }
                ],
            },
        )
        assert project.status_code == 201
        assert project.json()["attestation_trust_roots"][0]["key_id"] == KEY_ID
        review = client.post(
            f"/api/projects/{project.json()['id']}/reviews",
            json={"base_ref": base, "target_ref": target},
        ).json()
        obligation_id = review["evidence_obligations"][0]["id"]
        envelope = signed_envelope(private_key, statement(target))
        tampered = json.loads(json.dumps(envelope))
        payload = json.loads(base64.b64decode(tampered["payload"]))
        payload["predicate"]["verifiedLevels"] = ["SLSA_SOURCE_LEVEL_0"]
        tampered["payload"] = base64.b64encode(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        ).decode()

        denied = client.post(
            f"/api/reviews/{review['id']}/attestations/dsse",
            json={"obligation_ids": [obligation_id], "envelope": tampered},
        )
        assert denied.status_code == 409
        assert "no valid signature" in denied.json()["detail"]

        admitted = client.post(
            f"/api/reviews/{review['id']}/attestations/dsse",
            json={"obligation_ids": [obligation_id], "envelope": envelope},
        )
        assert admitted.status_code == 200
        evidence = admitted.json()["evidence"][-1]
        assert evidence["details"]["signature_verified"] is True
        replay = client.post(
            f"/api/reviews/{review['id']}/attestations/dsse",
            json={"obligation_ids": [obligation_id], "envelope": envelope},
        )
        assert replay.status_code == 409
        assert "already attached" in replay.json()["detail"]
        manifest = client.get(f"/api/reviews/{review['id']}/package").json()
        assert manifest["obligation_statuses"][0]["status"] == "satisfied"


def test_project_registration_rejects_a_malformed_ed25519_public_key(tmp_path: Path):
    repo, base, _ = create_capability_repo(tmp_path)
    with TestClient(create_app(tmp_path / "invalid-key.db")) as client:
        response = client.post(
            "/api/projects",
            json={
                "name": "Invalid trust root",
                "repo_path": str(repo),
                "head_ref": base,
                "test_command": [],
                "claims": [],
                "attestation_trust_roots": [
                    {
                        "key_id": "broken",
                        "algorithm": "ed25519",
                        "public_key_base64": "bm90LTMyLWJ5dGVz",
                        "verifier_id": VERIFIER_ID,
                        "authority": "security owner",
                        "resource_uri_prefix": RESOURCE_PREFIX,
                        "predicate_types": [VSA_TYPE],
                    }
                ],
            },
        )

        assert response.status_code == 422
        assert "32 bytes" in response.text


def test_signed_evidence_authority_must_match_the_affected_claim(tmp_path: Path):
    repo, base, target = create_capability_repo(tmp_path)
    private_key = Ed25519PrivateKey.generate()
    database = Database(tmp_path / "authority.db")
    service = ReviewService(database)
    project = service.create_project(
        name="Authority mismatch",
        repo_path=repo,
        head_ref=base,
        test_command=[],
        claims=[
            StructuralClaim(
                id="authority.task_scoped_only",
                title="Connectors use task-scoped capabilities",
                forbidden_modules=["legacy.workspace_credentials"],
                authority="security owner",
                evidence_obligations=[
                    {
                        "label": "signed verification",
                        "verification": "dsse_ed25519",
                        "required_verifier_id": VERIFIER_ID,
                        "required_verified_level": "SLSA_SOURCE_LEVEL_2",
                    }
                ],
            )
        ],
        attestation_trust_roots=[trust_root(private_key, authority="unrelated build owner")],
    )
    review = service.create_review(project.id, base_ref=base, target_ref=target)

    with pytest.raises(DecisionBlocked, match="authority"):
        service.attach_dsse_attestation(
            review.id,
            obligation_ids=[review.evidence_obligations[0].id],
            envelope=signed_envelope(private_key, statement(target)),
        )
