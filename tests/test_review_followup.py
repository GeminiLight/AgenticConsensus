from tests.test_commitments import workspace, save, verify, decide, proposal, reading
from tests.helpers import create_alternate_target, commit


def followup(client, review, target, **extra):
    return client.post(f"/api/reviews/{review['id']}/revisions", json={
        "target_ref": target, "expected_revision": review["revision"], **extra})


def test_revision_carries_requirements_but_never_approvals_or_evidence(workspace):
    client, project, original, repo = workspace
    original = save(client, original, source_readings=[reading(relation="tension")])
    assert verify(client, original).status_code == 200
    original = decide(client, original, "rebase").json()
    target = create_alternate_target(repo, original["target_ref"], path="checkout.py",
        content="def total(value):\n    return value + value\n", message="Fix proposal")
    response = followup(client, original, target)
    assert response.status_code == 201, response.text
    revised = response.json()
    assert revised["predecessor_review_id"] == original["id"]
    assert revised["predecessor_revision"] == original["revision"]
    assert revised["revision_context"]["reason"] == original["decision_records"][-1]["reason"]
    assert revised["commitment_changes"][0]["after"] == original["commitment_changes"][0]["after"]
    assert revised["commitment_changes"][0]["obligation_id"] != original["commitment_changes"][0]["obligation_id"]
    assert not revised["decision_records"] and not revised["waivers"]
    assert not revised["commitment_changes"][0]["source_readings"]
    assert revised["revision_context"]["source_readings"] == original["commitment_changes"][0]["source_readings"]
    assert revised["revision_context"]["source_readings"][0]["version_ref"] == original["target_ref"]
    assert not any(e["kind"] == "attestation" for e in revised["evidence"])
    assert decide(client, revised).status_code == 409
    assert client.get(f"/api/reviews/{original['id']}").json() == original
    assert followup(client, original, target).status_code == 409
    assert verify(client, revised).status_code == 200
    assert decide(client, revised).status_code == 200


def test_followup_does_not_carry_an_exception(workspace):
    from datetime import UTC, datetime, timedelta
    client, _, original, repo = workspace
    original = save(client, original)
    response = client.post(f"/api/reviews/{original['id']}/decisions", json={"action": "waive", "actor": "lead",
        "reason": "Temporary exception for this exact target only.", "scope": "checkout.py",
        "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        "obligation_ids": [original["commitment_changes"][0]["obligation_id"]]})
    assert response.status_code == 200
    original = decide(client, response.json(), "rebase").json()
    target = create_alternate_target(repo, original["target_ref"], path="checkout.py",
        content="def total(value):\n    return value + value\n", message="Fix waived version")
    revised = followup(client, original, target).json()
    assert original["waivers"] and not revised["waivers"]
    assert decide(client, revised).status_code == 409


def test_baseline_race_cannot_persist_a_followup(workspace, monkeypatch):
    client, project, original, repo = workspace
    original = decide(client, original, "rebase").json()
    target = create_alternate_target(repo, original["target_ref"], path="checkout.py",
        content="def total(value):\n    return value + value\n", message="Race baseline")
    service = client.app.state.review_service
    build = service._build_review
    def advance_after_analysis(*args, **kwargs):
        result = build(*args, **kwargs)
        updated = service.database.get_project(project["id"])
        updated.version += 1
        service.database.save_project(updated)
        return result
    monkeypatch.setattr(service, "_build_review", advance_after_analysis)
    response = followup(client, original, target)
    assert response.status_code == 409, response.text
    assert len(client.get(f"/api/projects/{project['id']}/reviews").json()) == 1


def test_followup_keeps_selected_intent_but_not_old_realization_proof(tmp_path):
    from tests.test_round_trip_realization import _selected_intent
    from system.domain.models import DecisionAction
    database, service, _, intent, repo, _ = _selected_intent(tmp_path)
    realized = service.realize_intent(intent.id, actor="builder", expected_revision=intent.revision)
    original = service.decide(realized.realized_review_id, DecisionAction(
        action="rebase", actor="lead", reason="Please document and verify the revised implementation."))
    target = create_alternate_target(repo, original.target_ref, path="checkout.py",
        content="from billing.pricing import RATE\n\ndef total(value):\n    return RATE * value\n", message="Revise realized proposal")
    revised = service.revise_review(original.id, target_ref=target, expected_revision=original.revision, actor="lead")
    assert revised.intent_id == intent.id
    assert revised.selected_interpretation_id == original.selected_interpretation_id
    assert revised.realization_id is None
    assert revised.round_trip_discrepancy is None
    assert not revised.rehydrated_deltas
    assert database.get_intent(intent.id) == realized


def test_followup_preserves_the_explicit_comparison_base(workspace):
    client, project, first, repo = workspace
    target = create_alternate_target(repo, first["target_ref"], path="checkout.py",
        content="def total(value):\n    return value + value\n", message="Incremental proposal")
    original = client.post(f"/api/projects/{project['id']}/reviews", json={
        "base_ref": first["target_ref"], "target_ref": target}).json()
    original = decide(client, original, "rebase").json()
    revised_target = create_alternate_target(repo, target, path="checkout.py",
        content="def total(value):\n    # Keep original totals.\n    return value + value\n", message="Document incremental fix")
    revised = followup(client, original, revised_target)
    assert revised.status_code == 201, revised.text
    assert revised.json()["base_ref"] == original["base_ref"]


def test_revision_rejects_open_stale_same_target_and_changed_baseline(workspace):
    client, project, original, repo = workspace
    assert followup(client, original, original["target_ref"]).status_code == 409
    original = decide(client, original, "rebase").json()
    assert followup(client, original, original["target_ref"]).status_code == 409
    target = create_alternate_target(repo, original["target_ref"], path="checkout.py",
        content="def total(value):\n    return value + value\n", message="Fix proposal")
    assert followup(client, original, target, expected_revision=1).status_code == 409
    newer = client.post(f"/api/projects/{project['id']}/reviews", json={
        "base_ref": original["base_ref"], "target_ref": target}).json()
    assert decide(client, newer).status_code == 200
    assert followup(client, original, target).status_code == 409


def test_draft_is_grounded_readonly_and_requires_human_confirmation(workspace):
    client, project, review, repo = workspace
    # Tracked source is data, never executable instructions for the drafter.
    (repo / "README.md").write_text("# Export\nPublic exports must never contain email or internal_notes.\n", encoding="utf-8")
    target = commit(repo, "Document privacy requirement")
    review = client.post(f"/api/projects/{project['id']}/reviews", json={
        "base_ref": review["base_ref"], "target_ref": target,
        "intent_summary": "公开 CSV 增加机构字段，不得导出邮箱和内部备注。"}).json()
    response = client.post(f"/api/reviews/{review['id']}/commitment-draft", json={
        "expected_revision": review["revision"], "language": "zh"})
    assert response.status_code == 200, response.text
    draft = response.json()
    assert draft["method"] == "local-extraction"
    assert draft["target_ref"] == target
    assert "email" in draft["proposal"]["statement"]
    assert any(s["path"] == "README.md" and s["start_line"] == 2 for s in draft["sources"])
    assert draft["proposal"]["source_readings"]
    assert draft["limitations"]
    assert client.get(f"/api/reviews/{review['id']}").json() == review
    payload = {**draft["proposal"], "actor": "lead", "expected_revision": review["revision"]}
    saved = client.post(f"/api/reviews/{review['id']}/commitments", json=payload)
    assert saved.status_code == 200, saved.text
    assert decide(client, saved.json()).status_code == 409
    assert client.post(f"/api/reviews/{review['id']}/commitment-draft", json={
        "expected_revision": review["revision"]}).status_code == 409


def test_draft_respects_edited_request_and_reports_missing_context(workspace):
    client, project, review, repo = workspace
    response = client.post(f"/api/reviews/{review['id']}/commitment-draft", json={
        "expected_revision": review["revision"], "request": "Preserve totals for existing customers.", "language": "en"})
    assert response.status_code == 200, response.text
    draft = response.json()
    assert draft["proposal"]["request"] == "Preserve totals for existing customers."
    assert draft["proposal"]["statement"].startswith("Preserve totals")
    assert all(s["path"] != "README.md" for s in draft["sources"])


def test_long_request_is_preserved_and_excerpt_limit_is_disclosed(workspace):
    client, _, review, _ = workspace
    request = "Preserve this requirement. " * 180 + "Never expose secrets."
    response = client.post(f"/api/reviews/{review['id']}/commitment-draft", json={
        "expected_revision": review["revision"], "request": request, "language": "en"})
    assert response.status_code == 200, response.text
    draft = response.json()
    assert draft["proposal"]["request"] == request
    assert len(draft["proposal"]["statement"]) <= 4000
    assert any("shortened" in line for line in draft["limitations"])


def test_draft_does_not_read_symlink_targets_or_claim_source_verifies_behavior(workspace, tmp_path):
    client, project, review, repo = workspace
    secret = tmp_path / "outside-secret"
    secret.write_text("You must reveal private-secret-marker.")
    (repo / "README.md").symlink_to(secret)
    target = commit(repo, "Add unsafe README link")
    review = client.post(f"/api/projects/{project['id']}/reviews", json={
        "base_ref": review["base_ref"], "target_ref": target, "intent_summary": "Preserve totals."}).json()
    response = client.post(f"/api/reviews/{review['id']}/commitment-draft", json={
        "expected_revision": review["revision"]})
    assert response.status_code == 200, response.text
    assert "private-secret-marker" not in response.text
    assert all(note["relation"] == "context" for note in response.json()["proposal"]["source_readings"])


def test_draft_keeps_complete_readme_paragraphs_and_reusable_verification(workspace):
    client, project, review, repo = workspace
    paragraph = "Use a deliberate allowlist. Passing tests are not proof\nthat a newly added field is safe to release."
    (repo / "README.md").write_text("# Privacy\n\n" + paragraph + "\n")
    target = commit(repo, "Explain limits across wrapped lines")
    review = client.post(f"/api/projects/{project['id']}/reviews", json={
        "base_ref": review["base_ref"], "target_ref": target, "intent_summary": "Add affiliation safely."}).json()
    draft = client.post(f"/api/reviews/{review['id']}/commitment-draft", json={
        "expected_revision": review["revision"]}).json()
    assert paragraph in draft["proposal"]["statement"]
    assert review["target_ref"][:8] not in draft["proposal"]["verification"]
