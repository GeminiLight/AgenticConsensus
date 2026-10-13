from __future__ import annotations

import argparse
import getpass
import json
import os
import sqlite3
import sys
import warnings
from datetime import UTC, datetime
from pathlib import Path

import uvicorn

from system.demo import seed_demo
from system.domain.transitions import DecisionBlocked
from system.paths import default_database_path, default_demo_repo_path, runtime_root
from system.services.database import (
    BackupValidationError,
    Database,
    DatabaseInUseError,
    RecordNotFound,
    database_maintenance_lock,
    database_runtime_lock,
)
from system.services.auth import (
    AuthConflict,
    AuthNotFound,
    AuthService,
    DevelopmentIdentity,
)
from system.services.llm import EvidenceSummarizer, LLMConfig
from system.services.review_service import ReviewService
from system.services.trust_signing import TrustSigningError, sign_trust_root_possession_files
from system.web.app import create_app


ROOT = runtime_root()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentic-consensus", description="Evidence-backed control for agentic code changes")
    parser.add_argument("--database", type=Path, default=default_database_path())
    commands = parser.add_subparsers(dest="command", required=True)

    serve = commands.add_parser("serve", help="run the local operator console")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument(
        "--secure-cookies",
        action="store_true",
        help="mark session cookies Secure when TLS terminates at this service or its proxy",
    )
    serve.add_argument(
        "--development-auth",
        action="store_true",
        help="bootstrap the local development administrator with admin/admin",
    )
    serve.add_argument(
        "--development-audit-identity",
        help="audit identity for the local development administrator",
    )

    demo = commands.add_parser("demo", help="seed a synthetic, fully analyzed Git scenario")
    demo.add_argument("--reset", action="store_true")
    demo.add_argument("--repo", type=Path, default=default_demo_repo_path())

    analyze = commands.add_parser("analyze", help="create a review package for a registered project")
    analyze.add_argument("--project", required=True)
    analyze.add_argument("--base", required=True)
    analyze.add_argument("--target", required=True)

    trust_admin = commands.add_parser(
        "grant-trust-admin",
        help="offline upgrade of an existing commit authority for trust-root management",
    )
    trust_admin.add_argument("--project", required=True)
    trust_admin.add_argument("--actor", required=True)
    trust_admin.add_argument("--reason", required=True)
    trust_admin.add_argument("--expected-version", type=int, required=True)

    authority_actor = commands.add_parser(
        "grant-authority-actor",
        help="offline addition of a registered local identity to an existing project authority grant",
    )
    authority_actor.add_argument("--project", required=True)
    authority_actor.add_argument("--authorizer", required=True)
    authority_actor.add_argument("--actor", required=True)
    authority_actor.add_argument("--reason", required=True)
    authority_actor.add_argument("--expected-version", type=int, required=True)

    backup = commands.add_parser("backup", help="create a verified database snapshot")
    backup.add_argument("--output", type=Path, required=True)
    backup.add_argument("--overwrite", action="store_true")

    restore = commands.add_parser("restore", help="restore a verified database snapshot")
    restore.add_argument("--input", type=Path, required=True)

    recover_password = commands.add_parser(
        "recover-password",
        help="offline recovery of one local identity with forced password replacement",
    )
    recover_password.add_argument("--username", required=True)
    recover_password.add_argument(
        "--operator",
        required=True,
        help="local host-operator label recorded in the identity audit",
    )
    recover_password.add_argument("--reason", required=True)
    recover_password.add_argument(
        "--password-env",
        help="environment variable holding the temporary password; otherwise prompt twice",
    )

    sign_proof = commands.add_parser(
        "sign-trust-proof",
        help="sign a trust-root possession package in an offline key environment",
    )
    sign_proof.add_argument("--template", type=Path, required=True)
    sign_proof.add_argument("--private-key", type=Path, required=True)
    sign_proof.add_argument("--output", type=Path, required=True)
    sign_proof.add_argument(
        "--password-env",
        help="name of an environment variable containing the PEM decryption password",
    )

    commands.add_parser("llm-smoke", help="run one bounded summary using synthetic evidence")
    return parser


def _read_recovery_password(password_env: str | None) -> str:
    if password_env:
        password = os.environ.get(password_env)
        if password is None:
            raise ValueError(f"password environment variable is not set: {password_env}")
        return password
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            password = getpass.getpass("New temporary password: ")
            confirmation = getpass.getpass("Confirm temporary password: ")
    except (EOFError, KeyboardInterrupt, getpass.GetPassWarning) as exc:
        raise ValueError(
            "secure password prompt is unavailable; use --password-env"
        ) from exc
    if password != confirmation:
        raise ValueError("temporary password confirmation does not match")
    return password


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "serve":
        loopback_hosts = {"127.0.0.1", "localhost", "::1"}
        if args.host not in loopback_hosts and not args.secure_cookies:
            print(
                "Refusing non-loopback service without secure cookies; "
                "terminate TLS and pass --secure-cookies.",
                file=sys.stderr,
            )
            return 2
        if args.development_auth and args.host not in loopback_hosts:
            print(
                "Development authentication requires a loopback host.",
                file=sys.stderr,
            )
            return 2
        if args.development_auth and not args.development_audit_identity:
            print(
                "Development authentication requires --development-audit-identity.",
                file=sys.stderr,
            )
            return 2
        if args.development_audit_identity and not args.development_auth:
            print(
                "--development-audit-identity requires --development-auth.",
                file=sys.stderr,
            )
            return 2
        development_identity = (
            DevelopmentIdentity(actor=args.development_audit_identity)
            if args.development_auth
            else None
        )
        print(f"AgenticConsensus is listening on http://{args.host}:{args.port}")
        print(f"Database: {args.database.resolve()}")
        if development_identity is not None:
            print(
                "Local development authentication is enabled for username admin "
                f"and audit identity {development_identity.actor}"
            )
        with database_runtime_lock(args.database):
            uvicorn.run(
                create_app(
                    args.database,
                    secure_cookies=args.secure_cookies,
                    development_identity=development_identity,
                ),
                host=args.host,
                port=args.port,
                log_level="info",
                # OAuth authorization codes and one-time state values arrive in
                # callback query strings. Uvicorn's default access log records
                # the complete request target, so keep it disabled instead of
                # persisting transient credentials in operator logs.
                access_log=False,
            )
        return 0
    if args.command == "demo":
        print("Creating an isolated Git scenario and collecting deterministic evidence…")
        with database_runtime_lock(args.database):
            result = seed_demo(args.database, args.repo, reset=args.reset)
        print(f"Project: {result.project_id}")
        print(f"Review:  {result.review_id}")
        print(f"Repo:    {result.repo_path}")
        if result.attestation_path:
            print(f"Signed VSA: {result.attestation_path}")
        print("Ready. Run `agentic-consensus serve` to review the blocked transition.")
        return 0
    if args.command == "analyze":
        with database_runtime_lock(args.database):
            review = ReviewService(Database(args.database)).create_review(
                args.project, base_ref=args.base, target_ref=args.target
            )
        print(json.dumps(review.model_dump(mode="json"), indent=2, ensure_ascii=False))
        return 0
    if args.command == "grant-trust-admin":
        try:
            with database_maintenance_lock(args.database):
                database = Database(args.database)
                project = ReviewService(database).grant_trust_administrator(
                    args.project,
                    actor=args.actor,
                    reason=args.reason,
                    expected_project_version=args.expected_version,
                )
                event = database.list_project_events(project.id)[-1]
        except (DatabaseInUseError, DecisionBlocked, RecordNotFound, ValueError) as exc:
            print(f"Trust-admin upgrade failed: {exc}", file=sys.stderr)
            return 2
        print(
            json.dumps(
                {
                    "project_id": project.id,
                    "project_version": project.version,
                    "event_id": event.id,
                    "granted_action": event.payload["granted_action"],
                    "actor": event.actor,
                    "authority": event.authority,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "grant-authority-actor":
        try:
            with database_maintenance_lock(args.database):
                database = Database(args.database)
                project = ReviewService(database).grant_authority_actor(
                    args.project,
                    authorizer=args.authorizer,
                    target_actor=args.actor,
                    reason=args.reason,
                    expected_project_version=args.expected_version,
                )
                event = database.list_project_events(project.id)[-1]
        except (DatabaseInUseError, DecisionBlocked, RecordNotFound, ValueError) as exc:
            print(f"Authority grant failed: {exc}", file=sys.stderr)
            return 2
        print(
            json.dumps(
                {
                    "project_id": project.id,
                    "project_version": project.version,
                    "event_id": event.id,
                    "event_action": event.action,
                    "authorizer": event.actor,
                    "target_actor": event.payload["target_actor"],
                    "authority": event.authority,
                    "granted_actions": event.payload["granted_actions"],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "backup":
        try:
            report = Database(args.database).backup(args.output, overwrite=args.overwrite)
        except (BackupValidationError, FileExistsError, OSError, ValueError) as exc:
            print(f"Backup failed: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0
    if args.command == "restore":
        try:
            report = Database(args.database, initialize=False).restore(args.input)
        except (BackupValidationError, DatabaseInUseError, OSError, sqlite3.Error, ValueError) as exc:
            print(f"Restore failed: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0
    if args.command == "recover-password":
        try:
            database_path = args.database.expanduser().resolve()
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
            recovery_path = database_path.with_name(
                f"{database_path.stem}.pre-password-recovery-{timestamp}{database_path.suffix}"
            )
            with database_maintenance_lock(database_path):
                database = Database(database_path, initialize=False)
                database.validate_snapshot(database_path)
                service = AuthService(database)
                temporary_password = _read_recovery_password(args.password_env)
                recovery_plan = service.prepare_password_recovery(
                    username=args.username,
                    operator=args.operator,
                    reason=args.reason,
                    new_password=temporary_password,
                )
                database.backup(recovery_path)
                user, event, revoked_sessions = service.recover_password(recovery_plan)
        except (
            AuthConflict,
            AuthNotFound,
            BackupValidationError,
            DatabaseInUseError,
            FileExistsError,
            OSError,
            sqlite3.Error,
            ValueError,
        ) as exc:
            print(f"Password recovery failed: {exc}", file=sys.stderr)
            return 2
        print(
            json.dumps(
                {
                    "target_user_id": user.id,
                    "target_actor": user.actor,
                    "target_role": user.role,
                    "password_change_required": user.password_change_required,
                    "revoked_sessions": revoked_sessions,
                    "event_id": event.id,
                    "recovery_backup": str(recovery_path),
                    "recovery_backup_validated": True,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "sign-trust-proof":
        try:
            template_path = args.template.expanduser().resolve()
            private_key_path = args.private_key.expanduser().resolve()
            output_path = args.output.expanduser().resolve()
            if output_path in {template_path, private_key_path}:
                raise TrustSigningError("output must differ from the template and private-key files")
            if output_path.exists():
                raise FileExistsError(f"output already exists: {output_path}")
            password = None
            if args.password_env:
                password_value = os.environ.get(args.password_env)
                if password_value is None:
                    raise TrustSigningError(
                        f"password environment variable is not set: {args.password_env}"
                    )
                password = password_value.encode()
            envelope, report = sign_trust_root_possession_files(
                template_path,
                private_key_path,
                password=password,
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("x", encoding="utf-8") as output:
                json.dump(envelope, output, indent=2, ensure_ascii=False)
                output.write("\n")
        except (FileExistsError, OSError, TrustSigningError) as exc:
            print(f"Trust-proof signing failed: {exc}", file=sys.stderr)
            return 2
        print(
            json.dumps(
                {
                    **report,
                    "output": str(output_path),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "llm-smoke":
        result = EvidenceSummarizer(LLMConfig.from_env()).summarize(
            {
                "patch_summary": "checkout.py | 4 lines changed",
                "tests": "pass",
                "findings": [
                    {
                        "kind": "forbidden_dependency",
                        "severity": "critical",
                        "status": "open",
                        "message": "New import crosses the billing service boundary",
                    }
                ],
            }
        )
        print(json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False))
        return 0 if result.source == "model" else 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
