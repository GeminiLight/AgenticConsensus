"""Run the actual browser intent model against regression cases."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_intent_model_behaviors():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is needed for browser model tests")
    result = subprocess.run(
        [node, "--test", str(Path(__file__).with_name("intent_model.test.cjs"))],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_intent_composer_has_focused_steps_and_explicit_clarification():
    root = Path(__file__).resolve().parents[1] / "system/web/static"
    html = (root / "index.html").read_text()
    js = (root / "app.js").read_text()
    assert 'id="intent-request-step"' in html
    assert 'id="intent-candidates-step"' in html
    assert 'id="intent-composer-back"' in html
    assert 'id="clarification-choices"' in html
    assert 'id="clarification-impact"' in html
    assert 'aria-labelledby="intent-dialog-title"' in html
    assert 'IntentModel.clarificationPayload' in js
    assert 'IntentModel.editCandidate' in js
    assert 'IntentModel.fromAIRun' in js
    assert 'renderClarificationHistory' in js
    assert 'intentDrafts' in js


def test_clarification_keeps_actions_outside_the_scrolling_fields():
    html = (Path(__file__).resolve().parents[1] / "system/web/static/index.html").read_text()
    clarification = html.split('id="clarification-form"', 1)[1].split('</form>', 1)[0]
    assert 'class="intent-composer-body"' in clarification
    assert 'class="intent-composer-footer"' in clarification


def test_pending_intent_save_protects_the_submitted_draft():
    js = (Path(__file__).resolve().parents[1] / "system/web/static/app.js").read_text()
    assert 'setIntentSaving(true)' in js
    assert 'setIntentSaving(false)' in js
    assert 'draft.saving' in js


def test_saved_proposal_editor_has_version_review_and_stable_actions():
    root = Path(__file__).resolve().parents[1] / "system/web/static"
    html = (root / "index.html").read_text()
    js = (root / "app.js").read_text()
    assert 'id="candidate-revision-dialog"' in html
    editor = html.split('id="candidate-revision-form"', 1)[1].split('</form>', 1)[0]
    assert 'class="intent-composer-body"' in editor
    assert 'class="intent-composer-footer"' in editor
    assert 'id="candidate-revision-latest"' in editor
    assert 'id="candidate-revision-rebase"' in editor
    assert 'IntentModel.revisionPayload' in js
    assert 'IntentModel.recordedRevision' in js
    assert 'edit-intent-candidate' in js
    assert 'add-intent-candidate' in js


def test_memory_drafts_are_scoped_to_the_authenticated_identity():
    js = (Path(__file__).resolve().parents[1] / "system/web/static/app.js").read_text()
    assert 'intentDraftOwner !== auth.user.id' in js
    assert 'intentDrafts.clear()' in js
    assert 'intentDrafts.get(draft.projectId) === draft' in js
    assert 'draft.ownerId === state.auth?.user?.id' in js
