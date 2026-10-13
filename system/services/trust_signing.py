from __future__ import annotations

import base64
import binascii
from copy import deepcopy
from hashlib import sha256
import hmac
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from system.services.attestation import (
    GENERIC_PAYLOAD_TYPE,
    STATEMENT_TYPE,
    TRUST_ROOT_POSSESSION_LEVEL,
    TRUST_ROOT_POSSESSION_POLICY_URI,
    VSA_PREDICATE_TYPE,
    pae,
)


SIGNATURE_PLACEHOLDER = "<replace-with-base64-ed25519-signature>"


class TrustSigningError(ValueError):
    pass


def _read_bounded(path: Path, *, label: str, max_bytes: int) -> bytes:
    try:
        if not path.is_file():
            raise TrustSigningError(f"{label} is not a regular file: {path}")
        size = path.stat().st_size
        if size <= 0 or size > max_bytes:
            raise TrustSigningError(f"{label} must contain between 1 and {max_bytes} bytes")
        return path.read_bytes()
    except OSError as exc:
        raise TrustSigningError(f"could not read {label}: {path}") from exc


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    value = {}
    for key, item in pairs:
        if key in value:
            raise TrustSigningError(f"signing package contains duplicate JSON field {key}")
        value[key] = item
    return value


def _reject_constant(value: str):
    raise TrustSigningError(f"signing package contains non-JSON constant {value}")


def _strict_json(payload: bytes, *, label: str) -> dict:
    try:
        value = json.loads(
            payload,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except TrustSigningError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TrustSigningError(f"{label} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise TrustSigningError(f"{label} must be a JSON object")
    return value


def _decode_base64(value: object, *, label: str, max_bytes: int) -> bytes:
    if not isinstance(value, str) or not value:
        raise TrustSigningError(f"{label} must be non-empty base64")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise TrustSigningError(f"{label} is not valid base64") from exc
    if len(decoded) > max_bytes:
        raise TrustSigningError(f"{label} exceeds {max_bytes} bytes")
    return decoded


def _require_exact_keys(value: dict, expected: set[str], *, label: str) -> None:
    if set(value) != expected:
        raise TrustSigningError(f"{label} does not match the canonical possession template")


def _validate_package(package: dict) -> tuple[dict, bytes, bytes]:
    _require_exact_keys(
        package,
        {"contract", "envelope", "signing_input_base64"},
        label="signing package",
    )
    contract = package.get("contract")
    envelope = package.get("envelope")
    if not isinstance(contract, dict) or not isinstance(envelope, dict):
        raise TrustSigningError("signing package contract and envelope must be objects")
    _require_exact_keys(
        contract,
        {
            "algorithm",
            "key_id",
            "public_key_base64",
            "project_head",
            "project_version",
            "verifier_id",
            "resource_uri",
            "policy_uri",
            "required_verified_level",
        },
        label="signing contract",
    )
    if contract.get("algorithm") != "ed25519":
        raise TrustSigningError("signing contract algorithm must be ed25519")
    for field in ("key_id", "project_head", "verifier_id", "resource_uri"):
        if not isinstance(contract.get(field), str) or not contract[field]:
            raise TrustSigningError(f"signing contract {field} is required")
    if not isinstance(contract.get("project_version"), int) or contract["project_version"] < 1:
        raise TrustSigningError("signing contract project_version must be positive")
    if contract.get("policy_uri") != TRUST_ROOT_POSSESSION_POLICY_URI:
        raise TrustSigningError("signing package does not use the required possession policy")
    if contract.get("required_verified_level") != TRUST_ROOT_POSSESSION_LEVEL:
        raise TrustSigningError("signing package does not use the required possession level")
    public_key = _decode_base64(
        contract.get("public_key_base64"),
        label="contract public key",
        max_bytes=32,
    )
    if len(public_key) != 32:
        raise TrustSigningError("contract public key must decode to exactly 32 bytes")

    _require_exact_keys(
        envelope,
        {"payloadType", "payload", "signatures"},
        label="DSSE envelope template",
    )
    if envelope.get("payloadType") != GENERIC_PAYLOAD_TYPE:
        raise TrustSigningError("DSSE envelope template has an unexpected payloadType")
    payload = _decode_base64(envelope.get("payload"), label="DSSE payload", max_bytes=2_000_000)
    statement = _strict_json(payload, label="DSSE payload")
    _require_exact_keys(
        statement,
        {"_type", "subject", "predicateType", "predicate"},
        label="in-toto Statement",
    )
    if statement.get("_type") != STATEMENT_TYPE or statement.get("predicateType") != VSA_PREDICATE_TYPE:
        raise TrustSigningError("signing package is not a SLSA VSA Statement")
    subjects = statement.get("subject")
    if not isinstance(subjects, list) or len(subjects) != 1 or not isinstance(subjects[0], dict):
        raise TrustSigningError("possession Statement must contain exactly one subject")
    subject = subjects[0]
    _require_exact_keys(subject, {"name", "digest"}, label="possession subject")
    digest = subject.get("digest")
    if subject.get("name") != "governed project head" or not isinstance(digest, dict):
        raise TrustSigningError("possession subject does not match the canonical template")
    _require_exact_keys(digest, {"gitCommit"}, label="possession subject digest")
    if digest.get("gitCommit") != contract["project_head"]:
        raise TrustSigningError("possession subject does not match the contracted project head")

    predicate = statement.get("predicate")
    if not isinstance(predicate, dict):
        raise TrustSigningError("possession predicate must be an object")
    _require_exact_keys(
        predicate,
        {
            "verifier",
            "resourceUri",
            "policy",
            "verificationResult",
            "verifiedLevels",
            "slsaVersion",
        },
        label="possession predicate",
    )
    verifier = predicate.get("verifier")
    policy = predicate.get("policy")
    if not isinstance(verifier, dict) or not isinstance(policy, dict):
        raise TrustSigningError("possession verifier and policy must be objects")
    _require_exact_keys(verifier, {"id"}, label="possession verifier")
    _require_exact_keys(policy, {"uri"}, label="possession policy")
    if verifier.get("id") != contract["verifier_id"]:
        raise TrustSigningError("possession verifier does not match the signing contract")
    if predicate.get("resourceUri") != contract["resource_uri"]:
        raise TrustSigningError("possession resource URI does not match the signing contract")
    if policy.get("uri") != TRUST_ROOT_POSSESSION_POLICY_URI:
        raise TrustSigningError("payload does not use the required possession policy")
    if predicate.get("verificationResult") != "PASSED":
        raise TrustSigningError("possession verificationResult must be PASSED")
    if predicate.get("verifiedLevels") != [TRUST_ROOT_POSSESSION_LEVEL]:
        raise TrustSigningError("payload does not use the required possession level")
    if predicate.get("slsaVersion") != "1.2":
        raise TrustSigningError("possession VSA must declare SLSA version 1.2")
    canonical_payload = json.dumps(
        statement, separators=(",", ":"), sort_keys=True
    ).encode()
    if not hmac.compare_digest(payload, canonical_payload):
        raise TrustSigningError("DSSE payload is not the canonical possession template")

    signatures = envelope.get("signatures")
    if not isinstance(signatures, list) or len(signatures) != 1 or not isinstance(signatures[0], dict):
        raise TrustSigningError("DSSE envelope template must contain one signature placeholder")
    _require_exact_keys(signatures[0], {"keyid", "sig"}, label="signature placeholder")
    if signatures[0].get("keyid") != contract["key_id"]:
        raise TrustSigningError("signature key ID does not match the signing contract")
    if signatures[0].get("sig") != SIGNATURE_PLACEHOLDER:
        raise TrustSigningError("signing package no longer contains the expected signature placeholder")
    expected_signing_input = pae(GENERIC_PAYLOAD_TYPE.encode(), payload)
    signing_input = _decode_base64(
        package.get("signing_input_base64"),
        label="signing input",
        max_bytes=2_100_000,
    )
    if not hmac.compare_digest(signing_input, expected_signing_input):
        raise TrustSigningError("signing input does not match the canonical DSSE PAE bytes")
    return envelope, signing_input, public_key


def sign_trust_root_possession_package(
    package_bytes: bytes,
    private_key_bytes: bytes,
    *,
    password: bytes | None = None,
) -> tuple[dict, dict]:
    package = _strict_json(package_bytes, label="signing package")
    envelope, signing_input, expected_public_key = _validate_package(package)
    try:
        private_key = serialization.load_pem_private_key(private_key_bytes, password=password)
    except (TypeError, ValueError) as exc:
        raise TrustSigningError("private key is not a readable PEM key with the supplied password") from exc
    if not isinstance(private_key, Ed25519PrivateKey):
        raise TrustSigningError("private key must be Ed25519")
    actual_public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    if not hmac.compare_digest(actual_public_key, expected_public_key):
        raise TrustSigningError("private key does not match the signing package public key")
    signed_envelope = deepcopy(envelope)
    signed_envelope["signatures"][0]["sig"] = base64.b64encode(
        private_key.sign(signing_input)
    ).decode()
    envelope_sha256 = sha256(
        json.dumps(signed_envelope, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    return signed_envelope, {
        "key_id": signed_envelope["signatures"][0]["keyid"],
        "envelope_sha256": envelope_sha256,
    }


def sign_trust_root_possession_files(
    template_path: Path,
    private_key_path: Path,
    *,
    password: bytes | None = None,
) -> tuple[dict, dict]:
    package_bytes = _read_bounded(
        template_path,
        label="trust signing package",
        max_bytes=3_000_000,
    )
    private_key_bytes = _read_bounded(
        private_key_path,
        label="private key",
        max_bytes=64_000,
    )
    return sign_trust_root_possession_package(
        package_bytes,
        private_key_bytes,
        password=password,
    )
