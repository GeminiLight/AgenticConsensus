from __future__ import annotations

import base64
import binascii
import json
from hashlib import sha256

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel

from system.domain.models import AttestationTrustRoot


VSA_PREDICATE_TYPE = "https://slsa.dev/verification_summary/v1"
STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
GENERIC_PAYLOAD_TYPE = "application/vnd.in-toto+json"
TRUST_ROOT_POSSESSION_POLICY_URI = (
    "https://agentic-consensus.local/policies/trust-root-possession/v1"
)
TRUST_ROOT_POSSESSION_LEVEL = "CONSENSUS_TRUST_ROOT_POSSESSION_V1"


class AttestationVerificationError(ValueError):
    pass


class VerifiedAttestation(BaseModel):
    key_id: str
    verifier_id: str
    authority: str
    subject_git_commit: str
    predicate_type: str
    resource_uri: str
    verification_result: str
    verified_levels: list[str]
    payload_type: str
    envelope_sha256: str


def pae(payload_type: bytes, payload: bytes) -> bytes:
    """DSSE v1 pre-authentication encoding."""
    return b"DSSEv1 %d %s %d %s" % (len(payload_type), payload_type, len(payload), payload)


def build_trust_root_possession_template(
    root: AttestationTrustRoot,
    *,
    project_head: str,
    project_version: int,
) -> dict:
    """Build the exact VSA payload and DSSE bytes an external key must sign."""
    statement = {
        "_type": STATEMENT_TYPE,
        "subject": [
            {
                "name": "governed project head",
                "digest": {"gitCommit": project_head},
            }
        ],
        "predicateType": VSA_PREDICATE_TYPE,
        "predicate": {
            "verifier": {"id": root.verifier_id},
            "resourceUri": f"{root.resource_uri_prefix}{project_head}",
            "policy": {"uri": TRUST_ROOT_POSSESSION_POLICY_URI},
            "verificationResult": "PASSED",
            "verifiedLevels": [TRUST_ROOT_POSSESSION_LEVEL],
            "slsaVersion": "1.2",
        },
    }
    payload = json.dumps(statement, separators=(",", ":"), sort_keys=True).encode()
    signing_input = pae(GENERIC_PAYLOAD_TYPE.encode(), payload)
    return {
        "contract": {
            "algorithm": "ed25519",
            "key_id": root.key_id,
            "public_key_base64": root.public_key_base64,
            "project_head": project_head,
            "project_version": project_version,
            "verifier_id": root.verifier_id,
            "resource_uri": f"{root.resource_uri_prefix}{project_head}",
            "policy_uri": TRUST_ROOT_POSSESSION_POLICY_URI,
            "required_verified_level": TRUST_ROOT_POSSESSION_LEVEL,
        },
        "envelope": {
            "payloadType": GENERIC_PAYLOAD_TYPE,
            "payload": base64.b64encode(payload).decode(),
            "signatures": [
                {
                    "keyid": root.key_id,
                    "sig": "<replace-with-base64-ed25519-signature>",
                }
            ],
        },
        "signing_input_base64": base64.b64encode(signing_input).decode(),
    }


def _decode_base64(value: object, *, field: str, max_bytes: int) -> bytes:
    if not isinstance(value, str) or not value:
        raise AttestationVerificationError(f"DSSE {field} must be non-empty base64")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise AttestationVerificationError(f"DSSE {field} is not valid base64") from exc
    if len(decoded) > max_bytes:
        raise AttestationVerificationError(f"DSSE {field} exceeds {max_bytes} bytes")
    return decoded


def _public_key(root: AttestationTrustRoot) -> Ed25519PublicKey:
    key_bytes = _decode_base64(root.public_key_base64, field="public key", max_bytes=32)
    if len(key_bytes) != 32:
        raise AttestationVerificationError(
            f"trusted Ed25519 key {root.key_id} must decode to exactly 32 bytes"
        )
    try:
        return Ed25519PublicKey.from_public_bytes(key_bytes)
    except ValueError as exc:
        raise AttestationVerificationError(f"trusted Ed25519 key {root.key_id} is invalid") from exc


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict:
    value = {}
    for key, item in pairs:
        if key in value:
            raise AttestationVerificationError(f"verified payload contains duplicate JSON field {key}")
        value[key] = item
    return value


def _reject_json_constant(value: str):
    raise AttestationVerificationError(f"verified payload contains non-JSON constant {value}")


def verify_dsse_vsa(
    envelope: dict,
    *,
    trust_roots: list[AttestationTrustRoot],
    expected_git_commit: str,
    required_verifier_id: str | None = None,
    required_verified_level: str | None = None,
    required_policy_uri: str | None = None,
) -> VerifiedAttestation:
    """Verify a DSSE Ed25519 signature before parsing and enforcing a SLSA VSA."""
    if not isinstance(envelope, dict):
        raise AttestationVerificationError("DSSE envelope must be a JSON object")
    payload_type = envelope.get("payloadType")
    if not isinstance(payload_type, str) or not (
        payload_type == GENERIC_PAYLOAD_TYPE
        or payload_type.startswith("application/vnd.in-toto.")
        and payload_type.endswith("+json")
    ):
        raise AttestationVerificationError("DSSE payloadType is not an in-toto JSON media type")
    payload = _decode_base64(envelope.get("payload"), field="payload", max_bytes=2_000_000)
    signatures = envelope.get("signatures")
    if not isinstance(signatures, list) or not 1 <= len(signatures) <= 32:
        raise AttestationVerificationError("DSSE signatures must contain between 1 and 32 entries")

    roots_by_key = {root.key_id: root for root in trust_roots}
    valid_roots: list[AttestationTrustRoot] = []
    signed_bytes = pae(payload_type.encode(), payload)
    for signature in signatures:
        if not isinstance(signature, dict):
            continue
        root = roots_by_key.get(signature.get("keyid"))
        if root is None:
            continue
        signature_bytes = _decode_base64(signature.get("sig"), field="signature", max_bytes=128)
        try:
            _public_key(root).verify(signature_bytes, signed_bytes)
        except InvalidSignature:
            continue
        valid_roots.append(root)
    if not valid_roots:
        raise AttestationVerificationError("DSSE envelope has no valid signature from a trusted key")

    try:
        statement = json.loads(
            payload,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except AttestationVerificationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AttestationVerificationError("verified DSSE payload is not valid JSON") from exc
    if not isinstance(statement, dict) or statement.get("_type") != STATEMENT_TYPE:
        raise AttestationVerificationError(f"in-toto statement type must be {STATEMENT_TYPE}")
    predicate_type = statement.get("predicateType")
    if predicate_type != VSA_PREDICATE_TYPE:
        raise AttestationVerificationError(f"predicateType must be {VSA_PREDICATE_TYPE}")

    subjects = statement.get("subject")
    if not isinstance(subjects, list) or not any(
        isinstance(subject, dict)
        and isinstance(subject.get("digest"), dict)
        and subject["digest"].get("gitCommit") == expected_git_commit
        for subject in subjects
    ):
        raise AttestationVerificationError("VSA subject does not match the review target Git commit")

    predicate = statement.get("predicate")
    if not isinstance(predicate, dict):
        raise AttestationVerificationError("VSA predicate must be an object")
    verifier = predicate.get("verifier")
    verifier_id = verifier.get("id") if isinstance(verifier, dict) else None
    if not isinstance(verifier_id, str) or not verifier_id:
        raise AttestationVerificationError("VSA verifier.id is required")
    if required_verifier_id and verifier_id != required_verifier_id:
        raise AttestationVerificationError(
            f"VSA verifier {verifier_id} does not match required verifier {required_verifier_id}"
        )

    eligible_roots = [
        root
        for root in valid_roots
        if root.verifier_id == verifier_id and predicate_type in root.predicate_types
    ]
    if not eligible_roots:
        raise AttestationVerificationError(
            "the verified signing key is not bound to this verifier and predicate type"
        )
    root = eligible_roots[0]
    resource_uri = predicate.get("resourceUri")
    expected_resource_uri = f"{root.resource_uri_prefix}{expected_git_commit}"
    if resource_uri != expected_resource_uri:
        raise AttestationVerificationError(
            f"VSA resourceUri does not match expected resource {expected_resource_uri}"
        )
    policy = predicate.get("policy")
    if not isinstance(policy, dict) or not isinstance(policy.get("uri"), str):
        raise AttestationVerificationError("VSA policy.uri is required")
    if required_policy_uri and policy["uri"] != required_policy_uri:
        raise AttestationVerificationError(
            f"VSA policy {policy['uri']} does not match required policy {required_policy_uri}"
        )
    verification_result = predicate.get("verificationResult")
    if verification_result != "PASSED":
        raise AttestationVerificationError("VSA verificationResult must be PASSED")
    verified_levels = predicate.get("verifiedLevels")
    if not isinstance(verified_levels, list) or not all(
        isinstance(item, str) and item for item in verified_levels
    ):
        raise AttestationVerificationError("VSA verifiedLevels must be a list of strings")
    if required_verified_level and required_verified_level not in verified_levels:
        raise AttestationVerificationError(
            f"VSA does not include required level {required_verified_level}"
        )

    envelope_digest = sha256(
        json.dumps(envelope, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    return VerifiedAttestation(
        key_id=root.key_id,
        verifier_id=verifier_id,
        authority=root.authority,
        subject_git_commit=expected_git_commit,
        predicate_type=predicate_type,
        resource_uri=resource_uri,
        verification_result=verification_result,
        verified_levels=verified_levels,
        payload_type=payload_type,
        envelope_sha256=envelope_digest,
    )
