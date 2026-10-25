from pathlib import Path
import re

from fastapi.testclient import TestClient

from system.web.app import create_app


def _assets(client: TestClient) -> tuple[str, str, str]:
    return (
        client.get("/").text,
        client.get("/static/app.js").text,
        client.get("/static/theme.css").text,
    )


def _relative_luminance(color: str) -> float:
    channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast_ratio(left: str, right: str) -> float:
    high, low = sorted((_relative_luminance(left), _relative_luminance(right)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def test_review_desk_has_one_project_switcher_and_no_global_sidebar(tmp_path: Path):
    with TestClient(create_app(tmp_path / "review-desk.db")) as client:
        html, javascript, _ = _assets(client)

        assert 'class="mobile-project-control project-switcher"' in html
        assert 'id="mobile-project-select"' in html
        assert '<aside class="sidebar">' not in html
        assert 'id="project-focus"' not in html
        assert 'class="canvas-toolbar"' not in html
        assert "function renderProjectFocus" not in javascript
        assert 'id="review-workbench"' in html
        assert 'id="review-canvas"' in html
        assert 'id="project-file-panel"' in html


def test_selected_review_leads_with_one_verdict_then_actions_then_checks(tmp_path: Path):
    with TestClient(create_app(tmp_path / "review-order.db")) as client:
        _, javascript, _ = _assets(client)

        render = javascript.split("function renderReview()", 1)[1].split("function showDialog", 1)[0]
        assert render.index("renderReviewVerdict") < render.index('class="decision-bar"')
        assert render.index('class="decision-bar"') < render.index("renderAdmission(manifest)")
        assert render.count("renderReviewVerdict(review, manifest)") == 1
        assert render.count("renderAdmission(manifest)") == 1
        assert 'class="decision-options"' not in render
        assert 'reviewDecisionBoundary(review, manifest)' in render
        assert 'data-action="rebase"' in render
        assert 'data-action="reject"' in render
        assert 'id="next-review-inspection"' in javascript
        assert 'DecisionModel.nextInspection' in javascript
        assert "Not ready to approve" in javascript
        assert "DecisionModel.requirementCoverage(review, manifest).heading" in javascript
        assert 'class="requirement-coverage"' in javascript
        assert "Only the configured checks have passed." in javascript
        assert "Ready to approve" not in javascript
        assert "Record approval" in javascript
        assert "Approval requires all blocking checks to pass." in javascript


def test_primary_navigation_has_four_clear_work_views(tmp_path: Path):
    with TestClient(create_app(tmp_path / "review-tabs.db")) as client:
        _, javascript, _ = _assets(client)

        tabs = javascript.split("function renderReviewWorkspaceTabs()", 1)[1].split("function setReviewWorkspaceTab", 1)[0]
        assert tabs.count('role="tab"') == 4
        for label in ("Decision", "Changes", "Evidence", "Audit"):
            assert f"<span data-i18n={label}>{label}</span>" in tabs
        assert "Ask AI" not in tabs
        assert "review?.changed_paths?.length" in tabs
        assert "evidenceCount" in tabs
        assert 'role="tablist" aria-label="Review sections"' in tabs
        assert 'aria-selected="true"' in tabs


def test_ai_uses_the_inspector_and_audit_has_a_dedicated_view(tmp_path: Path):
    with TestClient(create_app(tmp_path / "review-disclosures.db")) as client:
        html, javascript, _ = _assets(client)

        assert 'data-inspector-tab="files"' in html
        assert 'data-inspector-tab="assistant"' in html
        assert 'class="button button-with-icon open-ai-inspector-button"' in javascript
        assert 'setInspectorTab("assistant", { open: true, focus: true })' in javascript
        assert "function handleInspectorTabKeydown" in javascript
        assert 'id="review-panel-audit"' in javascript
        assert "Decision provenance" in javascript
        assert javascript.index("renderAdmission(manifest)") < javascript.index('id="review-panel-audit"')
        assert 'id="review-copilot-template"' in html
        assert 'id="contract-graph-template"' in html


def test_check_failures_are_first_and_passed_checks_are_collapsed(tmp_path: Path):
    with TestClient(create_app(tmp_path / "review-checks.db")) as client:
        _, javascript, _ = _assets(client)

        admission = javascript.split("function renderAdmission", 1)[1].split("function renderDecisionRecords", 1)[0]
        assert "const order = { block: 0, unknown: 1, pass: 2 }" in admission
        assert 'class="passed-checks"' in admission
        assert "attentionItems.map(checkRow)" in admission
        assert "passedItems.map(checkRow)" in admission
        assert admission.index("attentionItems.map(checkRow)") < admission.index("passedItems.map(checkRow)")
        assert "plainReviewCheckSummary" in javascript
        assert "No test command is configured for this project." in javascript


def test_loading_error_empty_and_permission_states_are_explicit(tmp_path: Path):
    with TestClient(create_app(tmp_path / "review-states.db")) as client:
        html, javascript, theme = _assets(client)

        assert "function renderReviewLoading" in javascript
        assert 'class="loading-skeleton loading-skeleton-title"' in javascript
        assert 'setAttribute("aria-busy", "true")' in javascript
        assert "function renderReviewError" in javascript
        assert "Couldn’t open this pull request" in javascript
        assert "retry-review-button" in javascript
        assert 'class="permission-notice" role="note"' in javascript
        assert "Read-only access" in javascript
        assert "No pull requests yet." in javascript
        assert "Decide what is safe to merge." in html
        assert ".review-loading, .review-error" in theme
        assert ".permission-notice" in theme


def test_empty_state_is_truthful_about_product_scope(tmp_path: Path):
    with TestClient(create_app(tmp_path / "empty-state.db")) as client:
        html = client.get("/").text
        empty = html.split('<section class="empty-state" id="empty-state">', 1)[1].split("</section>", 1)[0]

        assert "Analyze a GitHub pull request" in empty
        assert "Use a local repository" in empty
        assert "GitHub access is read-only" in empty
        assert "never merges code on your behalf" in empty
        assert "empty-orbit" not in empty
        assert "EVIDENCE-BACKED" not in empty


def test_file_tree_is_secondary_to_the_map_and_remains_available(tmp_path: Path):
    with TestClient(create_app(tmp_path / "file-tree.db")) as client:
        html, javascript, theme = _assets(client)

        assert 'id="toggle-file-panel-button" aria-label="Show review inspector"' in html
        assert 'id="file-panel-button-label" data-i18n=Inspector>Inspector' in html
        assert 'id="project-file-panel"' in html
        assert 'aria-label="Review inspector"' in html
        assert 'id="project-file-tree" role="region"' in html
        assert "function loadProjectTree" in javascript
        assert "function renderProjectTree" in javascript
        assert "function setFilePanelOpen" in javascript
        assert 'filePanelOpen: false' in javascript
        assert "filePanelWasWide && !filePanelIsWide" in javascript
        assert ".control-grid.files-collapsed .project-file-panel { display: none; }" in theme
        assert ".project-file-panel.open { display: flex; }" in theme


def test_canvas_scrolls_with_the_page_instead_of_trapping_the_wheel(tmp_path: Path):
    with TestClient(create_app(tmp_path / "scrolling.db")) as client:
        _, _, theme = _assets(client)

        canvas_rule = re.search(r"\.review-canvas\s*\{(?P<body>[^}]*)\}", theme).group("body")
        assert "overflow: visible" in canvas_rule
        assert "max-height" not in canvas_rule
        assert ".decision-bar { position: static; box-shadow: none; }" in theme
        assert "scrollbar-gutter: stable" in theme


def test_narrow_layout_keeps_pr_switching_above_the_canvas(tmp_path: Path):
    with TestClient(create_app(tmp_path / "mobile-layout.db")) as client:
        html, javascript, theme = _assets(client)

        mobile = theme.rsplit("@media (max-width: 820px)", 1)[1].split("@media (max-width: 560px)", 1)[0]
        assert ".review-rail { grid-row: 1;" in mobile
        assert ".review-canvas { grid-row: 2;" in mobile
        assert 'aria-controls="review-list-content"' in html
        assert 'id="review-list-toggle"' in html
        assert 'content.hidden = !expanded' in javascript
        assert "function selectReviewFromList" in javascript
        assert "scroll-snap-type: x proximity" not in mobile
        assert ".review-list { display: block; max-height: none; overflow: visible; }" in mobile
        assert "grid-template-columns: repeat(4, minmax(0, 1fr))" in mobile
        assert "grid-template-columns: minmax(0, 1fr)" in mobile


def test_editorial_theme_replaces_navy_gradients_and_card_soup(tmp_path: Path):
    with TestClient(create_app(tmp_path / "editorial-theme.db")) as client:
        html, _, theme = _assets(client)

        for retired in ("#08111f", "#0d1829", "#14233a", "--accent: #3b82f6", "--accent: #2563eb"):
            assert retired not in theme
        assert "linear-gradient" not in theme
        assert "radial-gradient" not in theme
        assert '<div class="grain"' not in html
        assert 'id="icon-sparkles"' not in html
        assert "--font-editorial:" in theme
        assert ".review-verdict h3" in theme and "var(--font-editorial)" in theme
        flattened = re.search(r"\.evidence-card, \.obligation-card, \.delta-card, \.claim-context, \.finding, \.patch-stat\s*\{(?P<body>[^}]*)\}", theme).group("body")
        assert "border-radius: 0" in flattened
        assert "box-shadow: none" in flattened


def test_light_and_dark_secondary_text_pass_aa_contrast(tmp_path: Path):
    with TestClient(create_app(tmp_path / "contrast.db")) as client:
        theme = client.get("/static/theme.css").text

        light = re.search(r'html\[data-theme="light"\], body\.paper-mode\s*\{(?P<body>.*?)\}', theme, re.DOTALL).group("body")
        dark = re.search(r'html\[data-theme="dark"\]\s*\{(?P<body>.*?)\}', theme, re.DOTALL).group("body")
        for block in (light, dark):
            values = dict(re.findall(r"--(ground|muted|dim):\s*(#[0-9a-fA-F]{6})", block))
            assert _contrast_ratio(values["muted"], values["ground"]) >= 4.5
            assert _contrast_ratio(values["dim"], values["ground"]) >= 4.5


def test_primary_type_is_readable_and_reserves_mono_for_metadata(tmp_path: Path):
    with TestClient(create_app(tmp_path / "type.db")) as client:
        _, _, theme = _assets(client)

        assert "font: 14px/1.55 var(--font-ui);" in theme
        assert re.search(r"\.review-intent-title\s*\{[^}]*font:\s*600 26px/1\.25 var\(--font-ui\)", theme)
        assert re.search(r"\.review-verdict h3\s*\{[^}]*font:\s*600 17px/1\.3 var\(--font-ui\)", theme)
        assert re.search(r"\.verdict-reason\s*\{[^}]*font-size:\s*14\.5px", theme)
        assert re.search(r"\.review-checks li small\s*\{[^}]*font-size:\s*12\.5px", theme)
        assert "font: 11px var(--font-code)" in theme


def test_primary_ui_avoids_internal_math_notation_and_template_labels(tmp_path: Path):
    with TestClient(create_app(tmp_path / "plain-language.db")) as client:
        html, javascript, _ = _assets(client)

        primary_html = html.split('<section class="workspace hidden" id="workspace">', 1)[1].split('<details class="project-tools"', 1)[0]
        render = javascript.split("function renderReview()", 1)[1].split("function showDialog", 1)[0]
        for token in ("C^", "ΔC", "ΔA", "ΔE", "Ψ", "Φ", "R_decision", "PULL REQUEST CANVAS", "REVIEW QUEUE"):
            assert token not in primary_html
            assert token not in render
        assert "Human decision" in html
        assert "New review" in html


def test_project_intake_uses_defaults_and_progressive_disclosure(tmp_path: Path):
    with TestClient(create_app(tmp_path / "project-intake.db")) as client:
        html, javascript, theme = _assets(client)
        intake = html.split('<dialog id="project-dialog"', 1)[1].split("</dialog>", 1)[0]

        assert "Review a pull request" in intake
        assert "Choose a repository and an open pull request" in intake
        assert intake.count('<details class="intake-disclosure"') >= 3
        assert "Defaults applied" in intake
        assert 'id="project-intake-selection"' in intake
        assert "function updateProjectIntakeReadiness" in javascript
        assert "function focusProjectIntake" in javascript
        assert ".project-intake-layout" in theme
        assert ".project-intake-dialog" in theme


def test_refined_workbench_progressively_reveals_complex_review_detail(tmp_path: Path):
    with TestClient(create_app(tmp_path / "progressive-review.db")) as client:
        html, javascript, theme = _assets(client)

        assert 'id="github-change-repository"' in html
        assert 'id="github-pull-request-search"' in html
        assert 'aria-labelledby="project-intake-title"' in html
        assert 'id="project-intake-settings"' in html
        assert 'settings.open = !githubActive' in javascript
        assert 'class="copilot-starters" aria-label="Suggested questions"' in html
        assert 'data-copilot-prompt="What blocks approval, and what should happen next?"' in html

        assert "function renderChangedFiles" in javascript
        assert 'class="diff-navigation" role="group" aria-label="Changed files"' in javascript
        assert 'Open full diff' in javascript
        assert "function renderEvidenceBrief" in javascript
        assert 'class="evidence-brief module"' in javascript
        assert 'No open findings' in javascript

        assert '#contract-graph-canvas, .contract-graph-table { height: 380px; }' in theme
        assert '.review-audit-panel .graph-search-form, .review-audit-panel .graph-zoom { display: none; }' in theme
        assert '.control-grid.graph-focus .graph-search-form { display: grid;' in theme


def test_github_install_return_and_source_tabs_remain_keyboard_operable(tmp_path: Path):
    with TestClient(create_app(tmp_path / "github-intake.db")) as client:
        html, javascript, _ = _assets(client)

        assert 'searchParams.get("installation_id")' in javascript
        assert 'searchParams.get("setup_action") === "install"' in javascript
        assert 'searchParams.delete("installation_id")' in javascript
        assert 'id="github-source-tab" type="button" role="tab"' in html
        assert 'id="local-source-tab" type="button" role="tab"' in html
        assert "function handleRepositorySourceTabKeydown" in javascript
        assert '["ArrowRight", "ArrowLeft", "Home", "End"]' in javascript


def test_grounded_ai_feedback_and_quality_controls_remain_available(tmp_path: Path):
    with TestClient(create_app(tmp_path / "ai-controls.db")) as client:
        html, javascript, theme = _assets(client)
        template = html.split('<template id="review-copilot-template">', 1)[1].split("</template>", 1)[0]

        assert template.index('id="review-copilot-output"') < template.index('id="review-copilot-form"')
        assert template.index('id="review-copilot-form"') < template.index('class="ai-eval-strip"')
        assert "Recorded activity in this project" in template
        assert 'role="group" aria-label="Recorded AI run statistics"' in template
        assert "Citation ID match" in template
        assert "not independent proof of answer correctness" in template
        assert 'name="deliberate"' in template
        assert "async function askReviewCopilot" in javascript
        assert "async function planEvidenceGaps" in javascript
        assert "async function recordAIFeedback" in javascript
        assert "window.prompt" not in javascript
        assert "function showAIFeedbackEditor" in javascript
        assert ".review-copilot" in theme


def test_theme_control_is_light_dark_only_and_persisted(tmp_path: Path):
    with TestClient(create_app(tmp_path / "themes.db")) as client:
        html, javascript, _ = _assets(client)
        bootstrap = client.get("/static/theme-bootstrap.js").text

        assert '<html lang="zh-CN" data-theme-preference="light" data-theme="light">' in html
        assert 'id="language-button" data-language-switch' in html
        assert '/static/i18n.js?' in html
        assert 'const THEME_PREFERENCES = ["light", "dark"]' in javascript
        assert 'safePreference = THEME_PREFERENCES.includes(preference) ? preference : "light"' in javascript
        assert 'new Set(["light", "dark"])' in bootstrap
        assert 'localStorage.setItem(key, "light")' in bootstrap
        assert "prefers-color-scheme: dark" not in bootstrap
        assert "System theme" not in html
        assert "0.17.0-review-desk" in html


def test_account_menu_and_review_more_menu_are_keyboard_accessible(tmp_path: Path):
    with TestClient(create_app(tmp_path / "menus.db")) as client:
        html, javascript, theme = _assets(client)

        assert 'id="more-actions-button"' in html
        assert 'aria-haspopup="menu"' in html
        assert 'id="secondary-actions" role="menu"' in html
        assert "function handleSecondaryActionsKeydown" in javascript
        assert 'id="review-more-button"' in javascript
        assert "function bindReviewMoreMenu" in javascript
        assert 'role="menuitem" tabindex="-1"' in javascript
        assert ".secondary-actions.open" in theme
        assert ".review-more-menu > div" in theme


def test_controls_have_names_and_coarse_pointer_touch_targets(tmp_path: Path):
    with TestClient(create_app(tmp_path / "accessibility.db")) as client:
        html, javascript, theme = _assets(client)

        assert 'aria-label="Show review inspector"' in html
        assert 'aria-label="Close review inspector"' in html
        assert 'aria-label="Switch to dark theme"' in html
        assert 'aria-label="Open account menu"' in html
        assert 'aria-label="Copy review link"' in javascript
        assert 'aria-label="Refresh review summary"' in javascript
        assert "@media (pointer: coarse)" in theme
        assert "min-height: 44px" in theme
        assert ".inspector-tabs button" in theme.split("@media (pointer: coarse)", 1)[1]
        assert 'class="skip-link"' in html


def test_interactive_controls_do_not_use_decorative_unicode_as_icons(tmp_path: Path):
    with TestClient(create_app(tmp_path / "icons.db")) as client:
        html = client.get("/").text
        buttons = re.findall(r"<button\b.*?</button>", html, re.DOTALL)

        for button in buttons:
            for glyph in ("＋", "×", "◐", "⌑", "☼"):
                assert glyph not in button
        close_buttons = [button for button in buttons if "data-close-dialog" in button and "icon-button" in button]
        assert len(close_buttons) >= 6
        assert all('href="#icon-x-circle"' in button for button in close_buttons)


def test_review_workspace_reduces_visible_conceptual_duplication(tmp_path: Path):
    with TestClient(create_app(tmp_path / "duplication.db")) as client:
        html, javascript, _ = _assets(client)

        assert "What needs your attention" not in html
        assert "Merge decision workspace" not in html
        assert "Choose a decision brief" not in html
        assert "review-risk-summary" not in javascript
        assert "review-next-step" not in javascript
        assert "review-progress" not in javascript


def test_project_canvas_is_the_landing_view_and_reviews_open_from_it(tmp_path: Path):
    with TestClient(create_app(tmp_path / "canvas-home.db")) as client:
        html, javascript, theme = _assets(client)

        assert 'id="project-canvas-template"' in html
        assert 'id="project-canvas" class="project-canvas-mount" role="img"' in html
        assert 'id="project-canvas-activity"' in html
        assert 'id="view-nav"' in html
        assert 'data-view-tab="canvas" aria-current="page"' in html
        assert 'data-view-tab="review"' in html and 'data-view-tab="governance"' in html
        assert 'id="governance-view"' in html
        assert 'viewMode: "canvas"' in javascript
        assert "function showProjectCanvas" in javascript
        assert "function showGovernance" in javascript
        assert "function setProjectView" in javascript
        assert "function renderProjectCanvas" in javascript
        assert "function projectCanvasElements" in javascript
        # landing on a project shows the canvas unless the URL names a review
        landing = javascript.split('const requested = params.get("review");', 1)[1].split("} catch", 1)[0]
        assert "reviews.find((item) => item.id === requested)" in landing
        assert "|| reviews[0]" not in landing
        assert "else showProjectCanvas();" in landing
        assert 'params.get("view") === "governance"' in landing
        # Selection inspects context without leaving the map; opening a review is explicit.
        assert '"tap", "node", (event) => selectCanvasObject(event.target.id())' in javascript
        assert '$("#canvas-open-review").onclick = () => selectReview(review.id)' in javascript
        # The same object data drives the accessible list and renderer-unavailable fallback.
        assert 'data-canvas-object="${esc(data.id)}"' in javascript
        assert "Use the panel to inspect every object and its relationships." in javascript
        assert 'data-view-tab="intents"' in html
        assert 'params.get("view") === "intents"' in landing
        assert 'id="shortcuts-button" type="button" role="menuitem"' in html
        assert 'class="rail-hint"' not in html
        assert ".project-canvas-mount" in theme
        assert ".view-nav button.active" in theme
        assert 'body[data-view="canvas"] .review-rail' in theme
