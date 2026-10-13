from __future__ import annotations

import base64
from copy import deepcopy
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from system.domain.models import AttestationTrustRoot
from system.main import main
from system.services.attestation import pae
from system.services.database import Database
from system.services.review_service import ReviewService
from tests.helpers import create_capability_repo


def signing_fixture(tmp_path: Path):
    repo, base, _ = create_capability_repo(tmp_path)
    database = Database(tmp_path / "signing.db")
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
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    root = AttestationTrustRoot(
        key_id="ci-source-ed25519-2027",
        public_key_base64=base64.b64encode(public_key).decode(),
        verifier_id="https://ci.example.test/verifiers/source-policy/v1",
        authority="security owner",
        resource_uri_prefix="git+https://example.test/acme/capability@",
    )
    package = service.build_trust_root_possession_template(project.id, new_root=root)
    template_path = tmp_path / "trust-possession-signing-package.json"
    template_path.write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")
    private_key_path = tmp_path / "trust-root-private.pem"
    private_key_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return service, project, root, package, template_path, private_key_path


def test_offline_cli_signs_a_template_that_the_trust_service_accepts(
    tmp_path: Path, capsys
):
    service, project, root, _, template_path, private_key_path = signing_fixture(tmp_path)
    output_path = tmp_path / "signed-possession-vsa.json"

    exit_code = main(
        [
            "sign-trust-proof",
            "--template",
            str(template_path),
            "--private-key",
            str(private_key_path),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    report_text = capsys.readouterr().out
    report = json.loads(report_text)
    assert report["key_id"] == root.key_id
    assert report["output"] == str(output_path.resolve())
    assert "PRIVATE KEY" not in report_text
    envelope = json.loads(output_path.read_text(encoding="utf-8"))
    assert envelope["signatures"][0]["sig"] != "<replace-with-base64-ed25519-signature>"
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


def test_offline_cli_reads_an_encrypted_private_key_password_from_a_named_environment_variable(
    tmp_path: Path, capsys, monkeypatch
):
    _, _, _, _, template_path, private_key_path = signing_fixture(tmp_path)
    private_key = serialization.load_pem_private_key(
        private_key_path.read_bytes(), password=None
    )
    private_key_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.BestAvailableEncryption(b"test-secret"),
        )
    )
    monkeypatch.setenv("TEST_TRUST_KEY_PASSWORD", "test-secret")
    output_path = tmp_path / "signed-with-encrypted-key.json"

    try:
        exit_code = main(
            [
                "sign-trust-proof",
                "--template",
                str(template_path),
                "--private-key",
                str(private_key_path),
                "--password-env",
                "TEST_TRUST_KEY_PASSWORD",
                "--output",
                str(output_path),
            ]
        )
    except SystemExit as exc:
        exit_code = int(exc.code)

    assert exit_code == 0
    assert output_path.is_file()
    assert "test-secret" not in capsys.readouterr().out


def test_offline_cli_rejects_a_private_key_that_does_not_match_the_package(
    tmp_path: Path, capsys
):
    _, _, _, _, template_path, _ = signing_fixture(tmp_path)
    wrong_key_path = tmp_path / "wrong-private.pem"
    wrong_key_path.write_bytes(
        Ed25519PrivateKey.generate().private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    output_path = tmp_path / "must-not-exist.json"

    exit_code = main(
        [
            "sign-trust-proof",
            "--template",
            str(template_path),
            "--private-key",
            str(wrong_key_path),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 2
    assert not output_path.exists()
    assert "does not match" in capsys.readouterr().err


def test_offline_cli_rejects_a_repurposed_or_reencoded_signing_package(
    tmp_path: Path, capsys
):
    _, _, _, package, _, private_key_path = signing_fixture(tmp_path)
    tampered = deepcopy(package)
    envelope = tampered["envelope"]
    payload = json.loads(base64.b64decode(envelope["payload"], validate=True))
    payload["predicate"]["policy"]["uri"] = (
        "https://example.test/policies/source-verification/v1"
    )
    encoded_payload = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    envelope["payload"] = base64.b64encode(encoded_payload).decode()
    tampered["signing_input_base64"] = base64.b64encode(
        pae(envelope["payloadType"].encode(), encoded_payload)
    ).decode()
    tampered_path = tmp_path / "repurposed-package.json"
    tampered_path.write_text(json.dumps(tampered, indent=2) + "\n", encoding="utf-8")
    output_path = tmp_path / "must-not-exist.json"

    exit_code = main(
        [
            "sign-trust-proof",
            "--template",
            str(tampered_path),
            "--private-key",
            str(private_key_path),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 2
    assert not output_path.exists()
    assert "possession policy" in capsys.readouterr().err


def test_offline_cli_does_not_overwrite_an_existing_output_without_confirmation(
    tmp_path: Path, capsys
):
    _, _, _, _, template_path, private_key_path = signing_fixture(tmp_path)
    output_path = tmp_path / "existing.json"
    output_path.write_text("operator-owned\n", encoding="utf-8")

    exit_code = main(
        [
            "sign-trust-proof",
            "--template",
            str(template_path),
            "--private-key",
            str(private_key_path),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 2
    assert output_path.read_text(encoding="utf-8") == "operator-owned\n"
    assert "already exists" in capsys.readouterr().err
