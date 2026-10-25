from pathlib import Path

from fastapi.testclient import TestClient

from system.web.app import create_app as create_secure_app
from system.services.ai_copilot import ConsensusCopilot
from system.services.database import Database
from system.services.llm import EvidenceSummarizer, LLMConfig
from system.services.review_service import ReviewService
from tests.helpers import create_billing_repo


def create_app(database_path: Path):
    return create_secure_app(database_path, require_authentication=False)


def test_blocker_can_be_repaired_by_audited_one_time_test_run(tmp_path: Path):
    repo, base, target = create_billing_repo(tmp_path)
    app = create_app(tmp_path / "repair-tests.db")

    with TestClient(app) as client:
        project = client.post(
            "/api/projects",
            json={
                "name": "Repairable review",
                "repo_path": str(repo),
                "head_ref": base,
                "test_command": [],
                "claims": [],
            },
        ).json()
        review = client.post(
            f"/api/projects/{project['id']}/reviews",
            json={"base_ref": base, "target_ref": target},
        ).json()
        assert next(item for item in review["evidence"] if item["kind"] == "tests")["status"] == "not_run"

        response = client.post(
            f"/api/reviews/{review['id']}/tests",
            json={"test_command": ["python3", "-m", "unittest", "-q"]},
        )

        assert response.status_code == 200
        repaired = response.json()
        assert next(item for item in repaired["evidence"] if item["kind"] == "tests")["status"] == "pass"
        assert repaired["revision"] == 2
        assert app.state.database.get_project(project["id"]).test_command == []
        assert [event.action for event in app.state.database.list_events(review["id"])] == [
            "create_review",
            "rerun_tests",
        ]


def test_copilot_fallback_names_the_available_test_repair_action(tmp_path: Path):
    repo, base, target = create_billing_repo(tmp_path)
    database = Database(tmp_path / "actionable-copilot.db")
    reviews = ReviewService(database)
    project = reviews.create_project(
        name="Actionable advice",
        repo_path=repo,
        head_ref=base,
        test_command=[],
        claims=[],
    )
    review = reviews.create_review(project.id, base_ref=base, target_ref=target)
    copilot = ConsensusCopilot(
        database,
        reviews,
        EvidenceSummarizer(LLMConfig(enabled=False)),
    )

    run = copilot.ask_review(
        review.id,
        question="What exact evidence is missing, and where should I fix it?",
        actor="reviewer",
        deliberate=False,
    )

    assert "Configure & run tests" in run.result["answer"]
    assert any(citation.id == "workflow:rerun-tests" for citation in run.citations)
    assert any("target commit" in check for check in run.suggested_checks)


def test_review_workspace_closes_the_real_user_dead_ends(tmp_path: Path):
    with TestClient(create_app(tmp_path / "journey-ui.db")) as client:
        html = client.get("/").text
        javascript = client.get("/static/app.js").text
        theme = client.get("/static/theme.css").text

        assert "/static/app.js?v=" in html

        # Paper view must own every surface token even when the saved app theme is dark.
        paper = theme.split("body.paper-mode {", 1)[1].split("}", 1)[0]
        for token in ("--panel:", "--panel-subtle:", "--control:", "--code:"):
            assert token in paper

        # The primary canvas must lead with the verdict and put repair before audit detail.
        render = javascript.split("function renderReview()", 1)[1].split("function showDialog", 1)[0]
        assert render.index("renderReviewVerdict") < render.index("renderAdmission(manifest)")
        assert render.index("renderAdmission(manifest)") < render.index('id="review-panel-audit"')
        assert 'class="button button-with-icon open-ai-inspector-button"' in render
        assert 'setInspectorTab("assistant", { open: true, focus: true })' in render

        # The missing-test blocker must offer an in-context repair flow.
        assert 'id="test-command-dialog"' in html
        assert 'id="test-command-form"' in html
        assert 'name="test_command" required autofocus' in html
        assert 'data-configure-tests' in javascript
        assert 'async function rerunReviewTests' in javascript
        assert '`/api/reviews/${reviewId}/tests`' in javascript
        assert 'requireReviewOperation(form)' in javascript
        assert "let testCommand;\n  try {\n    testCommand = parseCommand(form.elements.test_command.value);" in javascript
        assert '$("#test-command-error").textContent = error.message;' in javascript

        # Repository files are actions, not decorative tree rows.
        assert 'class="file-tree-file${changed ? " changed" : ""}" type="button"' in javascript
        assert 'data-file-path="${esc(node.path)}"' in javascript
        assert 'function openChangedFile' in javascript

        # Loaded diffs expose a reversible state instead of a dead-end reload label.
        assert 'aria-controls="unified-diff" aria-expanded="false"' in javascript
        assert 'Hide unified diff' in javascript
        assert 'Show unified diff' in javascript
        assert 'button.dataset.idleHtml = "Hide unified diff"' in javascript


def test_local_adoption_metrics_measure_time_to_first_decision_brief(tmp_path: Path):
    repo, base, target = create_billing_repo(tmp_path)
    with TestClient(create_app(tmp_path / "adoption.db")) as client:
        empty = client.get("/api/adoption").json()
        assert empty == {
            "projects": 0,
            "projects_with_review": 0,
            "activation_rate": 0.0,
            "median_seconds_to_first_review": None,
            "projects_with_second_review_within_7_days": 0,
        }
        project = client.post(
            "/api/projects",
            json={
                "name": "Activation metrics",
                "repo_path": str(repo),
                "head_ref": base,
                "test_command": [],
                "claims": [],
            },
        ).json()
        client.post(
            f"/api/projects/{project['id']}/reviews",
            json={"base_ref": base, "target_ref": target},
        )

        metrics = client.get("/api/adoption").json()
        assert metrics["projects"] == 1
        assert metrics["projects_with_review"] == 1
        assert metrics["activation_rate"] == 1.0
        assert metrics["median_seconds_to_first_review"] is not None
        assert metrics["median_seconds_to_first_review"] < 5
        assert metrics["projects_with_second_review_within_7_days"] == 0
