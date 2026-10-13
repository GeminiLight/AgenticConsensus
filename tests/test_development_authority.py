from pathlib import Path

import pytest

from system.domain.models import DecisionAction
from system.domain.transitions import DecisionBlocked
from system.main import main
from system.services.auth import AuthService
from system.services.database import Database, database_runtime_lock
from system.services.review_service import ReviewService
from tests.helpers import create_capability_repo


ADMIN_PASSWORD = "correct horse battery staple"
DEVELOPMENT_ACTOR = "developer@example.test"
ORIGINAL_AUTHORIZER = "security-lead@example.test"


def configured_project(tmp_path: Path, *, authorizer_actions: list[str]):
    repository, base_ref, target_ref = create_capability_repo(tmp_path)
    database = Database(tmp_path / "development-authority.db")
    AuthService(database).bootstrap(
        username="admin",
        actor=DEVELOPMENT_ACTOR,
        password=ADMIN_PASSWORD,
    )
    service = ReviewService(database)
    project = service.create_project(
        name="Development authority",
        repo_path=repository,
        head_ref=base_ref,
        test_command=[],
        claims=[],
        policy_id="security-change-control/v1",
        default_authority="security owner",
        authority_grants=[
            {
                "authority": "security owner",
                "actors": [ORIGINAL_AUTHORIZER],
                "actions": authorizer_actions,
            }
        ],
    )
    return database, service, project, base_ref, target_ref


def test_registered_identity_can_be_added_to_an_existing_authority_grant(tmp_path: Path):
    actions = [
        "commit",
        "waive",
        "rebase",
        "reject",
        "rollback",
        "attest",
        "manage_trust",
    ]
    database, service, project, base_ref, target_ref = configured_project(
        tmp_path,
        authorizer_actions=actions,
    )

    updated = service.grant_authority_actor(
        project.id,
        authorizer=ORIGINAL_AUTHORIZER,
        target_actor=DEVELOPMENT_ACTOR,
        reason="Authorize the registered local development identity for the synthetic workflow",
        expected_project_version=project.version,
    )

    assert updated.version == project.version + 1
    assert updated.authority_grants[0].actors == [
        ORIGINAL_AUTHORIZER,
        DEVELOPMENT_ACTOR,
    ]
    event = database.list_project_events(project.id)[0]
    assert event.action == "authority_actor_add"
    assert event.actor == ORIGINAL_AUTHORIZER
    assert event.payload == {
        "target_actor": DEVELOPMENT_ACTOR,
        "authority": "security owner",
        "granted_actions": actions,
    }

    review = service.create_review(project.id, base_ref=base_ref, target_ref=target_ref)
    rejected = service.decide(
        review.id,
        DecisionAction(
            action="reject",
            actor=DEVELOPMENT_ACTOR,
            authority="security owner",
            policy_id="security-change-control/v1",
            reason="Reject the synthetic proposal while validating the delegated authority path",
        ),
    )
    assert rejected.status == "rejected"
    assert rejected.decision_records[-1].actor == DEVELOPMENT_ACTOR
    assert rejected.decision_records[-1].provenance == "project_authority_grant"


def test_authority_actor_grant_rejects_an_unauthorized_authorizer(tmp_path: Path):
    actions = ["commit", "waive", "rebase", "reject", "rollback", "attest"]
    _, service, project, _, _ = configured_project(
        tmp_path,
        authorizer_actions=actions,
    )

    with pytest.raises(DecisionBlocked, match="manage project authority"):
        service.grant_authority_actor(
            project.id,
            authorizer=ORIGINAL_AUTHORIZER,
            target_actor=DEVELOPMENT_ACTOR,
            reason="Attempt authority delegation without an authorized authority manager",
            expected_project_version=project.version,
        )


def test_authority_actor_grant_rejects_an_unregistered_target(tmp_path: Path):
    actions = [
        "commit",
        "waive",
        "rebase",
        "reject",
        "rollback",
        "attest",
        "manage_trust",
    ]
    _, service, project, _, _ = configured_project(
        tmp_path,
        authorizer_actions=actions,
    )

    with pytest.raises(DecisionBlocked, match="registered active local identity"):
        service.grant_authority_actor(
            project.id,
            authorizer=ORIGINAL_AUTHORIZER,
            target_actor="missing@example.test",
            reason="Attempt authority delegation to an identity that was never registered",
            expected_project_version=project.version,
        )


def test_cli_grants_registered_actor_and_reports_the_audited_version(
    tmp_path: Path, capsys,
):
    actions = [
        "commit",
        "waive",
        "rebase",
        "reject",
        "rollback",
        "attest",
        "manage_trust",
    ]
    database, _, project, _, _ = configured_project(
        tmp_path,
        authorizer_actions=actions,
    )

    result = main(
        [
            "--database",
            str(database.path),
            "grant-authority-actor",
            "--project",
            project.id,
            "--authorizer",
            ORIGINAL_AUTHORIZER,
            "--actor",
            DEVELOPMENT_ACTOR,
            "--reason",
            "Authorize the registered local development identity for the synthetic workflow",
            "--expected-version",
            str(project.version),
        ]
    )

    assert result == 0
    output = capsys.readouterr()
    assert output.err == ""
    assert DEVELOPMENT_ACTOR in output.out
    assert '"project_version": 2' in output.out
    assert '"event_action": "authority_actor_add"' in output.out
    assert ADMIN_PASSWORD not in output.out


def test_cli_authority_grant_refuses_a_live_console(tmp_path: Path, capsys):
    actions = [
        "commit",
        "waive",
        "rebase",
        "reject",
        "rollback",
        "attest",
        "manage_trust",
    ]
    database, _, project, _, _ = configured_project(
        tmp_path,
        authorizer_actions=actions,
    )
    command = [
        "--database",
        str(database.path),
        "grant-authority-actor",
        "--project",
        project.id,
        "--authorizer",
        ORIGINAL_AUTHORIZER,
        "--actor",
        DEVELOPMENT_ACTOR,
        "--reason",
        "Authorize the registered local development identity for the synthetic workflow",
        "--expected-version",
        str(project.version),
    ]

    with database_runtime_lock(database.path):
        assert main(command) == 2

    assert "still in use" in capsys.readouterr().err
    assert database.get_project(project.id).version == project.version
