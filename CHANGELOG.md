# Changelog

All notable user-facing changes to AgenticConsensus are documented here.

## [0.22.3] - 2026-09-05

### Changed

- Blocking checks without concrete sub-items show their facts as tags (based on v42 · project is at v43; 1 stale record) instead of a sentence.
- The audit graph's detail panel appears only after an element is selected, and the lens description row is gone; the graph starts right under the lens buttons.
- The inspector header is just "Inspector"; identity notes in dialogs are plain sans with monospace reserved for signed contracts.

## [0.22.2] - 2026-09-04

### Changed

- One typographic voice per level. Serif is reserved for the page and verdict titles; module heads, the change and evidence briefs, and the audit graph head are plain sans; monospace appears only inside code chips for identifiers, paths, and hashes.
- The verdict explains blockers in one short sentence ("Blocked by a stale base, 1 open critical finding, and 2 missing evidence records.") and lists the four facts as a plain dotted row instead of bordered chips; the uppercase eyebrow is gone and the title itself carries the tone colour.
- Check rows hide their summary when the concrete items are listed beneath them, and those items are plain indented rows rather than cards inside cards.
- Required-evidence and finding metadata are tags (record type, verified level, waivable) instead of monospace sentences; evidence records keep one meta line.
- The assistant panel drops its heading and paragraph, shows the model chip and one line of scope, labels answers with the model and time only, and lists sources by name without internal ids.
- The canvas side panel has no empty placeholder or voids: stat cards with single-word labels, claims, reviews, and the legend at the bottom; the floating hint and legend pills left the graph.
- Governance claim metadata is a row of tags; the audit graph header no longer repeats the lens description.

## [0.22.1] - 2026-09-04

### Changed

- Keyboard shortcuts are reachable from the account menu, the command palette, and the `?` key; the hint footer under the review list is gone.
- The command palette button reads "Jump to… ⌘K" instead of a bare glyph.
- The canvas no longer repeats the project name and a sentence of explanation above the graph; the graph starts under the top bar, and the header with its call to action appears only while a project has no review.
- The review header drops the Canvas back button now that Canvas sits in the top navigation.

## [0.22.0] - 2026-09-04

### Changed

- A project now has three top-level views in the top bar: **Canvas**, **Reviews**, and **Governance**. The canvas is no longer an entry inside the review list; it fills the whole width with its side panel, Reviews shows the list, the review desk, and the inspector, and Governance is its own page with governed claims, trusted signing keys, and intent maps. The URL keeps the view (`?view=`) and the selected review.
- Canvas nodes use a lighter, calmer type: medium weight instead of bold, tighter line height, mono only for files, and long review titles truncated to one readable block with the full title in the side panel.
- The review rail's group labels are sentence case. On narrow screens the top bar gains a second row for the view navigation so the project name keeps its space.

## [0.21.0] - 2026-09-04

### Changed

- Entry points now follow the object they act on. Instance actions (account, users, GitHub connection, theme) stay in the top-right menu; project actions (switch project, project canvas, governance, one **New review**) sit at the project level; review actions (decision, changes, evidence, audit, assistant) live inside the review desk.
- **New review** is one contextual action. On a local project it opens the revision comparison with a link to the pull-request path; on a GitHub project it opens the pull-request picker; with no project it opens repository intake. The duplicate compare icon in the rail and the always-present canvas button are gone.
- **Project governance** replaces "Advanced project controls". It lives with the project canvas, opens by default there, is hidden inside a review, and now leads with the governed claims (status, scope, severity, evidence obligations, authority, and how many reviews touch each claim) before trusted signing keys and intent maps. The canvas side panel lists the same claims and selecting one highlights it in the graph.
- The inspector opens on the assistant, with the file tree as the second tab; on wide screens the canvas side panel no longer duplicates the review list that the rail already shows.

## [0.20.0] - 2026-09-04

### Changed

- The review desk now has one focal point. The verdict is a tinted hero card that carries the status, one sentence of reasoning, four fact chips, and the decision buttons as its footer; everything else sits in separate module cards on a quiet ground instead of stacked text separated by rules.
- Checks are icon rows: a status glyph, a short title, one line of explanation, and the resolving actions. Sub-items (findings, missing records) are compact rows inside the check, and the implied "human decision required" row is no longer listed while a review is open.
- The review header keeps a single serif title with one quiet line beneath it (proposer, file count, revisions); hashes and identifiers moved out of the rail, which now shows the title, a status, and a time.
- Evidence and Changes tabs are arranged as modules (Required evidence, Findings, Evidence records, Governing claims) with counts in their heads; explanatory paragraphs were removed in favour of one-line heads.
- The project canvas header collapses to one line and its side panel leads with three stat cards (needs a disposition, open, decided).

## [0.19.0] - 2026-09-04

### Added

- Entering a project now lands on a **project canvas**: the current project state in the centre, its governed claims around it, every review as a node coloured by status, and the files each review changes clustered beside it. The canvas unfolds from the centre when it opens, open reviews with a critical finding pulse, hovering a node or a list entry highlights its relations, and selecting a review opens the review desk. A claim or file shows which reviews touch it.
- The canvas keeps an at-a-glance panel (version, open and decided counts, governed claims) and a newest-first review list that mirrors the graph for keyboard and screen-reader users.
- The review rail gains a **Project canvas** entry, the review header a **Canvas** button, `0` returns to the canvas from anywhere, and the command palette lists it.

### Changed

- A review is opened only when the URL names one; otherwise the project opens on the canvas. The inspector stays hidden on the canvas and returns to its previous state when a review opens.

## [0.18.0] - 2026-09-04

### Added

- A command palette (`⌘K` or `Ctrl+K`, or the command button in the top bar) jumps to any review or section and runs review actions such as approve, request an update, reject, run tests, open on GitHub, copy the link or summary, ask the assistant, toggle the inspector, switch theme, or start a new review.
- A shortcuts sheet (`?`) lists every keyboard shortcut.
- The project switcher is a top-bar menu that shows each project's source, version, and repository, with entries to analyze a pull request or register a local repository. The native select remains on narrow screens.
- A slim progress bar at the top of the window shows while requests are in flight.
- The inspector file tree gains a filter once a repository has more than a dozen files.
- The review rail groups open and decided reviews when both exist.

### Changed

- The audit graph and its SVG export use the product palette (green for support and decisions, red for contests and findings, amber for authority, teal for claims) in light and dark themes instead of the previous blue scale, and restyle when the theme changes.
- The project header row is gone from the working view; the review starts directly under the top bar. Presentation view keeps the large project title.
- The inspector toggle moved into the top bar, and the Files and Ask AI buttons in the review header appear only while the inspector is hidden.
- Assistant answers render as paragraphs and numbered points instead of one block of text.

## [0.17.1] - 2026-09-04

### Added

- Diffs are syntax-highlighted for Python, JavaScript and TypeScript, shell, and data files, with file headers that stay pinned while you scroll, an expand-all and collapse-all control, and a copy-path action on every file.
- The inspector is resizable: drag its left edge between 280 and 560 pixels, double-click to reset, or use the arrow keys on the handle. The width is remembered per browser.
- The review rail shows file and open-finding counts, renders a skeleton while reviews load, and its compare action is an icon with a tooltip.
- Review section tabs stay pinned under the top bar, so switching sections never requires scrolling back up.
- AI answers show the model name in the assistant header and can be copied in one click.

### Changed

- The decision bar names the authority and policy a decision will be recorded under.
- The project header collapses to one line so the review itself starts higher on the page.
- Toasts carry a success or error tone.

## [0.17.0] - 2026-09-04

### Added

- Every blocking check on the Decision view now carries its resolution in place: missing required evidence offers **Attach evidence**, **Import signed VSA**, or **Bounded waiver**; an open critical finding offers **Show in diff** and **Bounded waiver**; missing tests offer **Run tests**; a stale base offers **Request an update**.
- The Changes view renders each file's diff inline with line numbers, added and removed colouring, and findings anchored to the file they concern. The raw unified patch remains one click away.
- The inspector lists the files changed in this review with added and removed counts above the repository tree.
- Keyboard shortcuts: `J` and `K` switch reviews, `1` to `4` switch sections, `/` focuses the audit-graph search.
- The review rail shows when each review was created, filters reviews once more than five exist, and marks reviews with open critical findings.

### Changed

- Check labels and summaries reflect the real state returned by the server. A blocking check reads "Critical finding needs a disposition · 1 open critical finding requires disposition" instead of a passed-state sentence.
- The verdict states exactly what blocks approval and reports files, structure, tests, and required-evidence coverage with status colours.
- Decision dialogs are titled by what they do (Approve and record this change, Record a bounded waiver, Request an update, Reject this change, Roll back the approval), explain the consequence, show the finding or obligation being waived, and prefill the waiver scope.
- Reviews are referenced by a stable short id or their GitHub pull-request label instead of a truncated internal id.
- A token-driven stylesheet pair replaces the remaining dark-theme rules. Light, dark, and presentation view share one geometry, and the audit-graph controls, intent maps, trust roots, evidence records, dialogs, and account menu are restyled for the light workspace.

### Fixed

- Evidence records no longer collide in a two-column grid, and intent-map cards render their metrics and candidates with proper styling.
- The account menu no longer overlaps its tooltip or truncates the audit identity.
- Repository tree file names are no longer clipped.
- Recorded decisions open by default on decided reviews, and decision confirmations use natural wording.
- Ask AI no longer falls back silently when the provider cuts a structured answer off at the token budget. Prompts now carry explicit length limits, a truncated answer is repaired with a larger compact budget, verbose provider payloads are shaped to the draft schema before validation (citation IDs are still verified against the context cards), the `CONSENSUS_LLM_MAX_TOKENS` ceiling is 2400, and a gateway failure is reported as `model_unavailable` with a plain-language note instead of a misleading validation flag.

## [0.16.0] - 2026-09-02

### Added

- Analyze an open GitHub pull request in one flow by choosing its repository and PR; the product fetches a read-only, server-verified snapshot and opens the decision brief automatically.
- See merge readiness, assessment coverage, the top three blockers or evidence gaps, and the next human action before opening technical details.
- Open the original GitHub pull request from its review and copy a concise decision brief for team handoff.
- Measure local activation rate, time to first decision brief, and seven-day repeat review use through an administrator-only endpoint.

### Changed

- Reorganized the workspace around pull-request decisions, with Overview, Changes, Ask AI, Evidence, and Audit graph panels plus a hideable project file drawer.
- Simplified repository intake with secure defaults, progressive disclosure, loading, empty, error, retry, and repository-access recovery states.
- Made AI provider status and advisory limits explicit while moving model-quality diagnostics behind an optional disclosure.
- Updated the academic light interface, typography, scrolling, keyboard tab behavior, and 390px responsive layout.

### Fixed

- Prevented draft pull requests from being analyzed or presented as ready to merge.
- Removed mobile horizontal overflow and the translucent flash when opening the project file drawer.
