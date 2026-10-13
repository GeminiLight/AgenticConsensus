from __future__ import annotations

import os
import base64
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from system.domain.models import Evidence, StructuralClaim
from system.services.attestation import pae
from system.services.database import Database
from system.services.review_service import ReviewService


@dataclass(frozen=True)
class DemoResult:
    project_id: str
    review_id: str
    repo_path: Path
    base_ref: str
    target_ref: str
    attestation_path: Path | None = None


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin"), "LANG": "C.UTF-8"},
    )
    return result.stdout.strip()


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def seed_demo(database_path: str | Path, repo_path: str | Path, *, reset: bool = False) -> DemoResult:
    database = Database(database_path)
    repo = Path(repo_path).expanduser().resolve()
    existing = database.find_project_by_repo(repo)
    if existing and not reset:
        reviews = database.list_reviews(existing.id)
        if not reviews:
            raise RuntimeError("demo project exists without a review; run with --reset")
        attestation_path = repo / ".agentic-consensus" / "signed-source-vsa.json"
        return DemoResult(
            existing.id,
            reviews[0].id,
            repo,
            reviews[0].base_ref,
            reviews[0].target_ref,
            attestation_path if attestation_path.is_file() else None,
        )

    if reset and existing:
        database.delete_project_data(existing.id)
    if repo.exists():
        marker = repo / ".agentic-consensus-demo"
        if not reset:
            raise RuntimeError("demo repository exists; run with --reset")
        if not marker.is_file():
            raise RuntimeError("refusing to reset a directory not created by AgenticConsensus")
        shutil.rmtree(repo)

    repo.mkdir(parents=True)
    (repo / ".agentic-consensus-demo").write_text("Synthetic repository; safe to recreate.\n", encoding="utf-8")
    (repo / "security").mkdir()
    (repo / "security" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "security" / "task_scope.py").write_text(
        "def get_task_token(task_id: str) -> str:\n"
        "    return f'task:{task_id}'\n",
        encoding="utf-8",
    )
    for module_name in ("reviewed_scope", "compat_scope"):
        (repo / "security" / f"{module_name}.py").write_text(
            "def get_task_token(task_id: str) -> str:\n"
            "    return f'task:{task_id}'\n",
            encoding="utf-8",
        )
    (repo / "token_consumer.py").write_text(
        "from security.task_scope import get_task_token\n\n\n"
        "def acquire(task_id: str) -> str:\n"
        "    return get_task_token(task_id)\n",
        encoding="utf-8",
    )
    (repo / "connector_registry.py").write_text(
        "PROVIDERS = {'calendar': 'security.task_scope'}\n", encoding="utf-8"
    )
    (repo / "test_registry.py").write_text(
        "import unittest\n\nfrom connector_registry import PROVIDERS\n\n\n"
        "class RegistryTest(unittest.TestCase):\n"
        "    def test_calendar_remains_task_scoped(self):\n"
        "        self.assertEqual(PROVIDERS['calendar'], 'security.task_scope')\n",
        encoding="utf-8",
    )
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "demo@agentic-consensus.local")
    _git(repo, "config", "user.name", "AgenticConsensus Demo")
    base_ref = _commit(repo, "C42: connectors use task-scoped capabilities")

    (repo / "connectors").mkdir()
    (repo / "connectors" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "connectors" / "archive.py").write_text(
        "from importlib import import_module\n\n\n"
        "def load_provider(provider_name: str):\n"
        "    return import_module(provider_name)\n",
        encoding="utf-8",
    )
    (repo / "connector_registry.py").write_text(
        "PROVIDERS = {\n"
        "    'calendar': 'security.task_scope',\n"
        "    'archive': 'legacy.workspace_credentials',\n"
        "}\n",
        encoding="utf-8",
    )
    target_ref = _commit(repo, "Agent proposal: add archive connector from configured provider")

    verifier_id = "https://agentic-consensus.local/demo-verifier/v1"
    resource_uri_prefix = "demo://task-scoped-capability-migration@"
    key_id = "demo-source-ed25519-2026"
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    statement = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [{"name": "demo source revision", "digest": {"gitCommit": target_ref}}],
        "predicateType": "https://slsa.dev/verification_summary/v1",
        "predicate": {
            "verifier": {"id": verifier_id, "version": {"demo-policy-engine": "1.0"}},
            "resourceUri": f"{resource_uri_prefix}{target_ref}",
            "policy": {"uri": "https://agentic-consensus.local/policies/claim-evidence/v1"},
            "verificationResult": "PASSED",
            "verifiedLevels": ["CONSENSUS_CLAIM_POLICY_V1"],
            "slsaVersion": "1.2",
        },
    }
    payload_type = "application/vnd.in-toto+json"
    payload = json.dumps(statement, separators=(",", ":"), sort_keys=True).encode()
    envelope = {
        "payloadType": payload_type,
        "payload": base64.b64encode(payload).decode(),
        "signatures": [
            {
                "keyid": key_id,
                "sig": base64.b64encode(private_key.sign(pae(payload_type.encode(), payload))).decode(),
            }
        ],
    }
    attestation_path = repo / ".agentic-consensus" / "signed-source-vsa.json"
    attestation_path.parent.mkdir()
    attestation_path.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")

    service = ReviewService(database)
    project = service.create_project(
        name="Task-scoped capability migration",
        repo_path=repo,
        repo_label="demo://task-scoped-capability-migration",
        head_ref=base_ref,
        test_command=["python3", "-m", "unittest", "-q"],
        policy_id="security-change-control/v1",
        default_authority="security owner",
        authority_grants=[
            {
                "authority": "security owner",
                "actors": ["security-lead@example.test"],
                "actions": [
                    "commit",
                    "waive",
                    "rebase",
                    "reject",
                    "rollback",
                    "attest",
                    "manage_trust",
                ],
            }
        ],
        attestation_trust_roots=[
            {
                "key_id": key_id,
                "algorithm": "ed25519",
                "public_key_base64": base64.b64encode(public_key).decode(),
                "verifier_id": verifier_id,
                "authority": "security owner",
                "resource_uri_prefix": resource_uri_prefix,
                "predicate_types": ["https://slsa.dev/verification_summary/v1"],
            }
        ],
        claims=[
            StructuralClaim(
                id="authority.task_scoped_only",
                title="Connectors may use only task-scoped capabilities",
                scope="connectors.*",
                introduced_version=37,
                forbidden_modules=["legacy.workspace_credentials"],
                rationale="A connector must not exercise authority beyond the capability grant of its current task.",
                artifact_anchors=[
                    {
                        "path": "security/task_scope.py",
                        "kind": "code",
                        "relation": "realizes",
                        "version_ref": base_ref,
                    },
                    {
                        "path": "connector_registry.py",
                        "kind": "config",
                        "relation": "realizes",
                        "version_ref": base_ref,
                    },
                ],
                evidence_obligations=[
                    {
                        "label": "signed source-policy verification for the target artifact version",
                        "verification": "dsse_ed25519",
                        "required_verifier_id": verifier_id,
                        "required_verified_level": "CONSENSUS_CLAIM_POLICY_V1",
                        "required_provenance_prefix": "dsse-ed25519:",
                    },
                    "attempted denial of an ungranted capability",
                ],
                authority="security owner",
            )
        ],
    )
    project.version = 42
    database.save_project(project)
    review = service.create_review(
        project.id,
        base_ref=base_ref,
        target_ref=target_ref,
        proposer="coding-agent/archive-connector",
        intent_summary="Add an archive connector without widening credential authority",
    )
    review.evidence.append(
        Evidence(
            kind="policy",
            status="unknown",
            outcome="inconclusive",
            summary="The only broad-token runtime trace belongs to an older artifact version",
            claim_ids=["authority.task_scoped_only"],
            artifact_ref=base_ref,
            provenance="runtime_trace/credential-resolution-018",
            freshness="stale",
            invalidated_reason="Trace predates the proposed archive connector",
            details={"required_next_evidence": "current credential-provenance trace"},
        )
    )
    database.save_review(review)
    intent = service.create_intent(
        project.id,
        request="Move the token consumer to the reviewed task-scope entry point without widening authority.",
        context="The owner requested an explicit interpretation before generating the patch.",
        base_ref=base_ref,
        created_by="architect-agent@example.test",
        candidates=[
            {
                "title": "Use the reviewed scope module",
                "summary": "Substitute security.reviewed_scope for the existing task-scope import.",
                "structural_delta": {
                    "kind": "python_import_substitution",
                    "path": "token_consumer.py",
                    "from_module": "security.task_scope",
                    "to_module": "security.reviewed_scope",
                },
                "uncertainties": ["Confirm the reviewed entry point preserves task-token semantics"],
                "provenance": "demo/architect-candidate-reviewed-scope",
            },
            {
                "title": "Use the compatibility module",
                "summary": "Route the import through security.compat_scope during migration.",
                "structural_delta": {
                    "kind": "python_import_substitution",
                    "path": "token_consumer.py",
                    "from_module": "security.task_scope",
                    "to_module": "security.compat_scope",
                },
                "uncertainties": ["Confirm when the compatibility path expires"],
                "provenance": "demo/architect-candidate-compat-scope",
            },
        ],
    )
    selected, eliminated = intent.candidates
    intent = service.clarify_intent(
        intent.id,
        actor="security-lead@example.test",
        question="Which entry point is the durable project-state interpretation?",
        answer="Use security.reviewed_scope; it preserves task-token semantics and is not transitional.",
        retained_candidate_ids=[selected.id],
        eliminated_candidate_ids=[eliminated.id],
        resolved_uncertainties={selected.id: list(selected.uncertainties)},
        expected_revision=intent.revision,
    )
    intent = service.select_intent_candidate(
        intent.id,
        candidate_id=selected.id,
        actor="security-lead@example.test",
        reason="The durable reviewed entry point preserves the declared task-scoped authority.",
        expected_revision=intent.revision,
    )
    service.realize_intent(
        intent.id,
        actor="builder-agent@example.test",
        expected_revision=intent.revision,
    )
    return DemoResult(project.id, review.id, repo, base_ref, target_ref, attestation_path)
