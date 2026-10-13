# Verified user journeys

These journeys define the product behavior that browser QA and interface changes should preserve.

## 0. Landing on the project canvas

A project has four top-level views: Canvas, Requests, Reviews, and Rules.
Requests contains Intent Maps; Rules contains project claims and signing trust.
Entering a project opens the overview, while the map frames the change needing
attention, then an unresolved intent, an open change, or shared state. Framing
does not silently select a record. The header names the open-review and attention
counts; **Review next change** opens the actual Decision brief and remains visible
when the inspector is hidden. **Focus** shows the selected object's
relevant context; **Project** restores the entire map, with an explicit object
count. Desktop groups shared state and claims on the left, proposed changes and
their originating intents in the middle, and affected files on the right;
compact screens use a vertical flow. Relations are labelled. Selecting any object inspects its
context without leaving the map; **Inspect review** explicitly opens the desk.
An attention-first object list mirrors the graph for keyboard users and remains
usable when rendering is unavailable. Search matches full requests, paths and
IDs; matches keep their immediate neighbors. Fit, zoom, and a hideable panel
provide orientation. Automatic framing keeps the selected object and relationship
text readable; explicit **Fit map** can zoom out to show a large neighborhood.
Changing map scope preserves focus on its control rather than scrolling into
the inspector. Search return preserves the query and restores the chosen result.
The panel's Files view browses the governed Git snapshot and connects files to
their reviews. An unchanged file appears with a **contains** relation, never an
invented **changes** relation. Switching inspector tabs retains that map context;
Project scope clears the temporary snapshot. Ordinary scrolling is not captured as zoom.
The **Canvas** tab or `0` returns from a review.

**Read snapshot** opens a focused, read-only file reader from a tracked file's
Canvas detail. Unchanged files in the review's Files panel use the same reader;
changed files continue to open Changes. The reader names its project and exact
snapshot, never reads the unsaved working copy, and never presents the baseline
as the proposed patch. Full path, commit, object and byte size are available in
Snapshot details. Search navigates matching lines; narrow screens initially wrap
long code, and the explicit Wrap lines control remains available. Closing or
Escape restores the originating file control and leaves the Canvas context intact.

The server admits only exact tracked paths at the current governed commit and
does not follow symbolic links or open submodule checkouts. Empty, binary or
non-UTF-8, oversized and unavailable files have distinct states. The preview
limit is 256 KiB and 3,000 displayed lines; a persistent toolbar notice names
the partial preview and search scope when longer content is clipped. A failed read can retry the same frozen
request; a changed snapshot requires reloading the workspace. Closing, project
navigation or a changed sign-in clears private content and ignores late results.

The **Requests** view is a first-class workflow for request clarification,
candidate selection and bounded realization. **Rules** contains claims and
trusted signing keys, not the authoring workflow.

In **Rules**, expand a claim to inspect the evidence requirements configured
for the current project state. Source details disclose verifier, required level,
provenance prefix and waiver boundaries without implying that the claim status
approves a proposed change. Related reviews are matched by project-scoped claim
deltas or frozen requirement references. **Inspect evidence** opens that review’s
actual requirements; **Back to governing claim** restores the expanded claim and
keyboard focus. Empty and unavailable review context remain distinct, and retry
does not submit analysis or change recorded evidence.

Success means the reviewer understands what is open, what is blocked, and how each change relates to the governed claims before opening any single review.

## 1. First-time local evaluator

The evaluator clones the repository, installs the development dependencies, seeds the synthetic Git scenario, starts the loopback service, creates an administrator, and reaches a blocked review without configuring an LLM. The deterministic summary must make the product useful before any API key is supplied.

Success means the current change, review status, two blockers, evidence coverage, and disabled commit action are understandable without opening trust administration.

For a local repository, **New review** first explains its two sources: a GitHub
pull request or local revisions. **Local revisions** opens the named-project
comparison. A pending analysis or saved result reopens directly instead of hiding
its receipt behind source selection. Browser history navigation closes the source
choice with its old context. GitHub-backed projects continue directly to PR intake.
Enter
the target branch/tag/commit and change intent; the governed baseline and proposer
remain editable under **Baseline and proposer**. Analysis resolves both revisions
and runs project tests against the target; it does not merge the change. The
GitHub alternative is a separate route, not part of the submit footer.

Closing the panel keeps a per-project draft in this tab; reload/sign-out clears
it, and **Discard draft** explicitly removes it. An in-flight analysis shows its
submitted snapshot read-only when reopened. Project navigation closes the panel,
and a late completion cannot overwrite another project or newer session. A saved
review whose details fail to load retains an **Open review** receipt; that action
retries reads without submitting another analysis. On narrow screens, fields
scroll independently of the action footer and keyboard focus keeps the entire
input visible.

## 2. Architect resolving language-mediated intent

The architect creates an Intent Map with the original request, declared base, context, and at least two candidate import substitutions. A clarification may revise or eliminate candidates and must preserve its question, answer, actor, resolved uncertainty, and before/after snapshots. An active candidate is explicitly selected before realization becomes available.

In **Requests → New request**, first describe the desired change and what must stay
true. The repository baseline is prefilled and editable in a disclosure. Then
write alternatives or review interpreter drafts; every alternative has its own
file, current/replacement import, explanation, open questions and source. AI
drafting is advisory and discloses use of the configured remote provider.
Closing and reopening preserves a per-project draft while the page stays open;
reload and sign-out do not preserve drafts. Slow AI responses cannot overwrite
new edits, and saving protects the exact version being submitted.

**Clarify questions** keeps all active interpretations by default. Check only
questions that the answer settles; uncheck an interpretation only when the
answer rules it out. The impact summary previews those choices. A fully
resolved interpretation can be explicitly selected even when another remains
unresolved; selection records the other as not selected, not as disproven.
**Edit proposal** corrects a saved active interpretation; **Add alternative**
records another human-authored approach. Both keep every active alternative open,
preserve the original request and base, and require an attributed reason. Model
confidence is cleared when a draft is edited. Neither action selects a candidate,
changes repository files, invokes AI, or starts realization. Selected and realized
requests are locked. The 20-interpretation limit includes ruled-out alternatives.

The focused editor keeps a scrollable body separate from its action footer.
Closing and reopening preserves per-proposal drafts in the current tab; reload,
sign-out or changing identity clears them. A version conflict preserves input
and offers **Review latest revision**. Compare changes since the draft and your
edits to apply, then explicitly apply your edits to the latest version. Fields
you did not edit keep the collaborator's latest values. Applying edits is not
saving. An uncertain save result must be checked before retrying; the exact
attributed record can confirm that it was already saved, preventing duplicates.

**Decision trail** exposes the attributed question/answer or change/reason,
revised/added outcomes, readable field-level comparisons and full before/after
snapshots. Human selection remains a separate recorded action.

Success means the interface never silently collapses ambiguity into one patch and the complete path from request to selected structural interpretation remains inspectable.

## 3. Builder realizing a bounded structural change

The builder realizes the selected candidate. The caller worktree remains unchanged while the product creates a proposal commit in an isolated worktree, rehydrates candidate deltas from the real diff, computes round-trip discrepancy and observable coverage, and opens the linked review. Unsupported or stale operations retain failed preconditions and create no review.

Success means the Intent Map shows the proposal ref, real diff, selected rehydration, $D_{rt}$, coverage, and review linkage without presenting round-trip agreement as semantic correctness.

## 4. Reviewer investigating a blocked proposal

An open blocked review opens the **Decision** brief. **Changes** is a focused file-reading surface; **Evidence** contains obligations and records; **Audit** offers the Evidence coverage graph lens. The reviewer can trace source artifacts and evidence to the governed claim there. A missing Canvas dependency automatically exposes the complete relation table.

Decision leads with a compact status and one read-only **next inspection**:
a moved baseline, a critical finding in its actual changed file, missing evidence,
test/structure checks, or other recorded concerns. This is a deterministic
navigation aid, not AI advice or a completed-review checklist. It never runs a
test, calls a model, records a waiver or grants approval. Passing checks lead to
reading the change, not automatic approval. Closed reviews lead to their history;
missing decision attribution is explicitly disclosed rather than invented.

Each attention check has a native disclosure; the first is initially open and
the other checks and passed-check records remain available. **Decision options**
is secondary and initially closed while blocked. It retains the existing explicit
Request update, Reject and disabled Approve controls. Read-only users do not get
empty decision controls; approved reviews retain the explicit rollback action.
Evidence inspections reset temporary record filters and focus the appropriate
evidence-view tab. Keyboard users can open disclosures and reach their actions.

Every blocking check lists the concrete items behind it together with the action that resolves it in place: attach or import required evidence, record a bounded waiver, run the configured tests, show a finding in the diff, or request a rebase. **Show in diff** selects the relevant file and focuses the finding after its target-side code line. Locations outside the displayed patch are explicitly file-level; they are not attached to a similarly numbered deleted line.

Changes shows one file at a time, with path search, a native file selector and previous/next controls. The optional right inspector opens on **Files**; **Assistant** remains a separate tab. Changing files resets code scroll, while filtering preserves the search input and its native composition state. Empty files, binary changes, missing patches, truncated patches and retryable errors have distinct states. Patch metadata, governing claims and the full available raw patch remain accessible through disclosures. Closing the raw patch does not hide a truncation warning. A file is not marked reviewed merely because it was opened, and AI does not acquire approval authority.

Evidence separates **To resolve** (coverage for a closed review), **Records**, and **Claims**. The first view explains each unmet requirement beside its governing claim and collection action; satisfied or waived requirements remain available in a disclosure. Missing, stale, contested and unavailable coverage are distinct. Record search includes full source and canonical identifiers; **Needs attention** includes inconclusive, outdated and server-invalidated records. Requirement-to-record links apply an exact membership filter, which can be cleared without losing keyboard focus. Full provenance and record metadata are expandable, not truncated behind hover text. **Refresh records** retrieves the current review and admission result without running checks or invoking a model.

Collection dialogs name the target revision and explain that attaching a record does not execute tests or approve the review. A draft survives closing and reopening the same requirement in the current tab; another target/requirement, reload or sign-out clears it. After an ambiguous network failure, refresh Records before retrying. Signed evidence is still verified by the server. Retrospectively revoked signing trust is projected as invalidated evidence in the manifest and cannot appear as current support in the record filter.

Success means unknown or stale evidence is not presented as pass, the UI explains why commit remains blocked, and the reviewer never has to leave the blocker to resolve it.

## 5. Decision owner auditing a completed transition

A committed, rejected, rebased, waived, or rolled-back review defaults to the **Decision trail** lens. The owner can trace proposal, changed artifacts, governed claim, authority, recorded dispositions, and current state. Duplicate action labels receive deterministic suffixes so decisions remain distinguishable.

Success means actor, authority, policy, rationale, status, and provenance can be reconstructed from the review and event records.

## 6. Evidence auditor preparing a paper figure

Paper view opens the **Full contract** lens, uses the same API payload as the operator console, hides runtime account and proposer identity plus local paths, and keeps semantic relation labels visible. The auditor can download a deterministic 1600px SVG whose node labels match the interactive graph.

Success means the figure distinguishes proposal, artifacts, evidence, claim, authority, decisions, and state without implying that visual proximity changes governance semantics.

## 7. Keyboard and assistive-technology user

The user can reach all controls by keyboard, open the command palette with `⌘K` or `Ctrl+K` to jump to any review, section, or action, press `?` for the shortcut sheet, press `J` and `K` to move between reviews, `1` to `4` to switch review sections, `/` to focus graph search, switch between graph and relation table, activate a table node, read its metadata and connected relations, and restore the full view. Lens buttons expose pressed state and dynamic status text is announced.

Review filters belong to each project for the current signed-in page session.
Switching projects or using Back restores that project's query; sign-out or
reload clears it. Results report matching and total counts. `J`/`K` follow the
displayed result order, wrap within matches, and do nothing with no matches.
Returning from Canvas chooses a matching review or explains the empty search.
Editing an empty query keeps search available even if the list has shrunk;
explicit Clear restores focus to search or an available review.

Success means Canvas is never the only information channel and focus does not become trapped.

## 8. Mobile reviewer

On wide screens the inspector can be resized by dragging its left edge or with the arrow keys on the handle, and the width is remembered. At 390px, account operations move into the **More** menu while review and graph controls remain available. Lens, search, zoom, table, and export controls use at least 44px targets. The document does not overflow horizontally. Canvas can pan independently, and the relation table remains available when precision is more important than spatial navigation.

Below 821px, a selected review leads with its own content. **Switch review** expands
a vertical list with complete titles and current-row indication; six or more reviews
also expose a filter. Selection closes the list and focuses the selected heading.
Escape closes the list and returns to its switcher. A failed selection keeps the
list available; a successful retry restores the same focused reading state.
Decision, Changes, Evidence, and Audit fit on one row even at 320px; their counts
remain available to assistive technology when space is too narrow to show them.
Closing the Files/Assistant inspector returns to its opener. Crossing the responsive
breakpoint transfers focus between the switcher and the selected desktop row.

Success means the graph begins within the first task section and exposes meaningful content in the first viewport after scrolling to it.

## 9. Administrator and recovery operator

An administrator creates, disables, enables, and resets local identities without obtaining project authority implicitly. A host operator performs password recovery only while the service is stopped, with a verified pre-change backup and a forced password replacement on next login.

Success means credentials never enter audit payloads, sessions are revoked where required, and global role changes cannot bypass project authority grants.

On an explicitly opted-in preview, a new user may instead choose **Sign up** and bind a username, audit identity, and password to an operator profile. This grants console access only. Project authority remains a separate, explicit grant. Self-signup remains disabled on ordinary local instances.

## 10. GitHub pull-request reviewer

An administrator or operator clicks **Analyze pull request** and connects GitHub. On an unprovisioned self-hosted instance, the administrator completes GitHub's App Manifest page once; the browser then continues through account authorization and installation without exposing configuration fields. Later operators enter GitHub authorization directly. The reviewer searches the repositories explicitly granted to the installation, chooses one open pull request, and starts analysis. The product fetches the exact GitHub base and head revisions into a managed checkout, creates or reuses the governed project, and opens a decision brief containing merge readiness, assessment coverage, top risks or missing evidence, and the next human action.

The intake shows one picker at a time. Before GitHub is connected, focus stays on
the connection action and unavailable search/analysis controls are hidden. Choosing
a repository opens its PR list with a **Change** action to return to repositories.
PRs can be searched by title, number, branch or author; drafts remain visibly
unavailable. Selecting a row preserves keyboard focus and reveals **Analyze PR**.
Repository changes clear the previous PR choice. Late responses cannot overwrite
the latest selection or a reopened dialog. The body scrolls independently of the
actions; long names wrap and small-screen inputs retain a readable size. Required
fields inside collapsed settings are revealed by native form validation.

Once submitted, the picker becomes a named operation with its repository and PR
context. **Close** hides this view; it does not cancel the request. A persistent
status control (including a short visible label on mobile) reopens it. Keep the
browser page open to receive completion: this is not a durable background-job
service. An unchanged original view may open the result automatically; after the
user leaves or reopens it, completion offers **Open review** without taking over
their current work.

A saved result whose follow-up read fails retains that action, which retries reads
without resubmitting analysis. An interrupted or server-error response is explicitly
uncertain. **Check workspace** reads saved projects and reviews, matching the GitHub
repository/installation, PR URL and exact base/head commits before offering a result.
It never reruns analysis. Returning to settings from this state requires an explicit
warning acknowledgment. Rejected submissions keep their editable input and focused
error. Sign-out or session replacement clears private operation state and prevents
old completions from modifying the next session's form.

Local registration uses the same operation lifecycle but leads to **Open project**;
its copy describes reading the checkout, not PR analysis or approval.

Success means the first useful result requires only repository and PR selection; retry and access-recovery states remain actionable; selecting the same unchanged PR reuses its review; no App secret or user token appears in API output, SQLite plaintext, Git command arguments, persisted remotes, logs, or UI; an inaccessible repository or PR cannot be imported by changing an ID; and remote write operations are absent.

## 11. Reviewer using advisory assistance

The reviewer opens **Assistant** in the optional right inspector. The heading
identifies the selected review, revision, project version, and target. Advice is
not approval. Suggested questions only fill the composer; they never submit a
model request. **Ask assistant** sends the question and bounded review context to
the configured provider, as disclosed beside the action. Without a provider,
**Explain from records** uses local rules. **Find recorded gaps** is always local
and lists next checks without executing them. Optional challenge and synthesis
calls are tucked into **Answer options**.

Questions, answer options, selected history, and unsaved human edits belong to
their project and review during the signed-in page session. Returning to a review
restores them; sign-out, session replacement, or a page reload clears transient
drafts. Pending work belongs to its submitted context. Switching reviews does not
put a late answer or feedback confirmation into the new review, and requests
from earlier revisions release their controls without presenting stale advice as
current. A single earlier-version saved answer remains discoverable in history,
but its body and current-context actions are withheld until a new answer exists.

The submitted question stays above its answer. Source disclosures retain complete
available excerpts and offer navigation only to canonical records: findings in
their changed file, evidence in the searchable records view, requirements, claim
context, or decision context. Matching an ID means the record exists, not that it
supports the model's claim. **Edit & keep** displays and copies the kept human
answer while retaining the original in a disclosure; sources remain attributed to
that original answer. Feedback never approves a review or becomes evidence.

Read-only users can inspect saved advice and sources but cannot request or record
new advice. Errors preserve input and distinguish connectivity, permission,
context changes, and service failures. Metrics failure does not erase a completed
answer. The narrow inspector scrolls independently; 44px targets, visible focus,
and Escape-to-opener support pointer and keyboard use.

Success means the reviewer understands which review and processing mode they are
using, can inspect the original records, and can resume unfinished work without
mixing contexts or mistaking AI advice for governed authority.

## Browser acceptance matrix

| State | Expected default | Required evidence |
|---|---|---|
| Ambiguous intent | Intent workspace | candidate alternatives, uncertainty, clarification action |
| Selected intent | Intent workspace | actor, reason, selected candidate, bounded realization action |
| Realized intent | Linked review | proposal ref, artifact diff, Psi candidates, D_rt, coverage |
| Open and blocked | Evidence coverage | blockers, stale/unknown evidence, disabled commit |
| Open and committable | Scoped evidence coverage | enabled human decision, with unrecorded/unverified requirements explicitly warned about; no blanket safety claim |
| Terminal review | Decision trail | authority, disposition, current state |
| Paper view | Full contract | clean identity-safe graph and SVG |
| Canvas unavailable | Relation table | every visible relation, no blank state |
| No search match | Current lens retained | clear inline no-match message |
| 390px viewport | Compact controls | no page overflow, 44px targets |
| GitHub first use | Browser sign-in | admin Manifest confirmation, automatic OAuth continuation, no configuration fields |
| GitHub connected | Repository picker | account, access control, searchable explicit repository list |
| GitHub repository selected | Pull-request picker | open PRs, base/head context, retry and access recovery |
| Pull request analyzed | Decision brief | readiness, coverage, risks, next action, GitHub link |
| GitHub disconnected | Local governed copy | imported project remains usable, remote access removed |
| Assistant empty | Scoped question composer | visible review/version, provider disclosure, suggested questions do not submit |
| Assistant pending | Honest operation status | no duplicate request; late answer/feedback belongs to submitted context |
| Assistant saved | Version-checked answer | history, navigable canonical sources, semantic-support warning |
| Assistant human-edited | Kept advice plus original | displayed/copied edit, preserved original, no approval or evidence mutation |

## Requirement drafting and revision follow-up

Passing configured checks does not prove behavioral coverage. A review with no
recorded commitments presents its change intent as still unverified, with a
**Draft a verifiable commitment** action. Drafting reads bounded, immutable README
and base/target source, relevant test excerpts and recorded check outcomes. With a
configured model it fills an editable statement, rationale and concrete verification
plan, with cited risks. Model/provider provenance is visible; unavailable or invalid
model responses explicitly fall back to local extraction without a risk verdict.
Neither mode produces evidence or approval. Existing edits are kept unless the
user explicitly accepts a replacement. The full original request is preserved;
any statement shortening and limited source coverage are disclosed.

After **Request update**, **Review revised version** asks only for the new target.
It preserves the request, selected intent reference, commitments and verification
requirements, and links both reviews. Prior findings and source readings remain
clearly historical; decisions, waivers, attestations, old source anchors, and
realization results never become evidence for the new target. Tests run afresh.
If the project baseline advanced, the operator must reconcile against that
baseline in a new review rather than silently transplanting old commitments.

Once the revision is approved, both history links and the project workspace lead
to its recorded outcome. They no longer ask for another approval. A long draft
scrolls inside the editor while its save/cancel actions remain visible.

**Analyze risks** is an explicit action in the decision panel, not a background
model call. Each risk shows its impact, suggested check and actual source/check
references. Advice remains separate from configured checks and human evidence.
Saved current-version analysis survives reload; changed versions require fresh
analysis. A failed network refresh preserves the last saved answer and offers a
retry. Answers arriving after navigation, revision changes or sign-out cannot
overwrite the active context. In the commitment editor, risk detail starts
collapsed so the editable requirement remains the main task.
