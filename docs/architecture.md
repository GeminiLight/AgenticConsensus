# Architecture

AgenticConsensus is a local-first FastAPI application backed by SQLite. It separates observation, evidence admission, authority, and state transition so that an advisory model cannot silently become a decision maker.

```text
Language request + context version
        |
        v
Versioned Intent Map ---> clarification ---> explicit candidate selection
        |                                      |
        |                                      v
        |                         bounded Phi in isolated Git worktree
        |                                      |
        |                         proposal commit + real artifact diff
        |                                      |
        +<---- D_rt + coverage <---- independent AST Psi
                                               |
                                               v
Registered Git repository
        |
        v
Deterministic analyzers ----> evidence and findings
        |                              |
        v                              v
Versioned review package ------> admission checks
        |                              |
        |                         project authority
        |                              |
        v                              v
Contract Graph API <---------- decision transition
        |
        +--> interactive Canvas
        +--> accessible relation table
        +--> deterministic SVG
        +--> reviewer-safe JSON export

Canonical review context cards
        |
        +--> Review Copilot proposal --> independent critic --> synthesis
        +--> deterministic evidence-gap planner
        +--> Intent candidate interpreter
        |
        v
Advisory run + citations + model metadata --> feedback --> eval aggregates
        |
        +-- no governed transition authority
```

## Components

- `system/domain/` defines versioned intent, interpretation, clarification, realization, rehydration, project, review, claim, evidence, finding, decision, graph, AI advisory-run, citation, feedback, and evaluation models.
- `system/services/` implements bounded realization and rehydration, Git analysis, GitHub App authorization and managed cloning, evidence verification, state transitions, authentication, SQLite persistence, backup and recovery, trust-root lifecycle, structured model adapters, and the evidence-grounded Copilot orchestrator.
- `system/web/` exposes authenticated JSON endpoints and the operator console.
- `system/main.py` provides local service, demo, analysis, delegation, backup, restore, recovery, and offline signing commands.
- `tests/` verifies authorization boundaries, transition invariants, signed evidence, recovery, API behavior, UI contracts, and release metadata.

## Trust boundaries

Repository content and model output are untrusted input. Git commands use explicit argument arrays and registered roots. Evidence can satisfy an obligation only through its declared admission contract. The authenticated session supplies the actor for governed mutations; request bodies cannot impersonate another identity. Product roles decide console access, while project grants independently decide who may attest, waive, commit, roll back, or manage trust.

SQLite is the authoritative local state. Intent, project, review, event, trust, and authentication writes are version checked or transactionally protected. Advisory summary writes use review-revision compare-and-swap and commit their audit event in the same transaction, so a slow model response cannot overwrite a newer governed transition. Copilot runs and feedback are persisted separately from governed audit events and cannot mutate evidence, review status, or project state. Successful realization atomically persists the updated Intent, linked review, and review-creation event; a stale Intent removes its attempt-scoped proposal ref instead of leaving an orphaned package. Active duplicate base/target reviews are rejected under the same SQLite write reservation. Backup and restore validate hashes, SQLite integrity, model shape, and ownership links, including advisory-run and feedback ownership.

## AI advisory boundary

`ConsensusCopilot` builds an immutable, hashed context from canonical review objects. Cards have stable typed IDs such as `claim:*`, `evidence:*`, `finding:*`, `obligation:*`, `admission:*`, and `diff:*`. Model stages may cite only IDs in that context. Unknown IDs, missing citations, malformed structured output, network failure, or an incomplete critic/synthesizer sequence fail closed to a deterministic response.

Intent interpretation returns unsaved `InterpretationCandidate` objects sharing one source import and file but proposing distinct destination modules. Evidence-gap planning remains deterministic because missing and stale records are control-plane facts, not model judgments. Review deliberation is bounded to proposal, critic, and synthesis calls; there is no tool loop and no mutation tool exposed to the model.

Each advisory run records a context hash, prompt version, provider/model, source or fallback path, latency, token usage, resolved citations, citation precision, a mechanical faithfulness score, quality flags, and authenticated actor. Feedback is an upserted accepted/edited/rejected record. Aggregate evals are operational signals, not proof of semantic correctness; release checks still require fixture tests, adversarial citation tests, and human review.

The browser's `AssistantModel` owns transient questions, options, answer selection,
and feedback-editor drafts by authenticated session plus project/review identity.
Pending operations snapshot the submitted revision, project version, and target;
responses cannot select an answer in another review or survive an authentication
boundary. Saved advice is rendered only against its matching current version.
Source navigation resolves canonical record IDs, never arbitrary model URLs or
mutation commands. Kept human edits remain distinct from the original answer and
its sources. None of these presentation states changes governed records.

GitHub is an optional external identity and repository-discovery boundary, not a replacement for local product authentication. If the instance has no App credentials, an administrator starts a GitHub App Manifest handshake from the product. A hashed one-time state binds the cross-site registration callback to that administrator; the returned client secret is encrypted as a singleton configuration while the unused PEM and webhook secret are discarded. The same callback immediately starts the normal PKCE-protected user flow. Subsequent operators skip provisioning and enter OAuth directly. Both callback types remain independent of the strict local session cookie. Repository and pull-request API results are revalidated server-side; the browser cannot nominate an arbitrary clone URL or revision. Managed checkouts use credential-free HTTPS origins and a temporary `GIT_ASKPASS` environment. Pull-request analysis fetches the declared base branch plus `refs/pull/{number}/head`, verifies both fetched object IDs against the current GitHub metadata, and compares the merge base with the immutable head. Imported projects retain provider, repository, installation, default-branch, visibility, actor, and import-time provenance after the GitHub connection is removed.

## Intent and round-trip boundary

An Intent Map preserves the request and its context version alongside at least two candidate Python import substitutions. Clarification records snapshot candidates before and after attributed revisions, additions, eliminations, and resolved uncertainty. Only an explicitly selected active candidate may enter realization.

The current `Phi` supports exactly one single-line Python `from X import ...` module substitution whose source line and destination module are verifiable at the declared base. It creates a temporary Git worktree, commits there, retains the commit under `refs/agentic-consensus/proposals/*`, and leaves the registered worktree unchanged. `Psi` does not reuse the proposal object: it compares the artifact diff through an independent AST pass and returns candidate structural deltas or explicit ambiguity. The service records `D_rt` and observable coverage and links intent, selection, realization, rehydration, review, and later disposition by stable IDs. This is a bounded synchronization path, not general code generation or a semantic-correctness oracle.

## Contract Graph

`/api/reviews/{review_id}/graph` projects the same governed state used by admission and decision services. For realized intents it includes intent, selected interpretation, realization, rehydration, round-trip relation, version state, proposal, artifacts, structural claims, evidence, findings, authorities, and decisions. The browser does not maintain a separate mock graph.

The Canvas uses a vendored Cytoscape.js build. Decision, evidence, and full-contract lenses are presentation filters only; they never remove facts from the API or mutate the review. The relation table is the accessible and dependency-failure fallback. SVG export is deterministic and excludes registered local paths.

## Commitment drafting and linked revisions

`POST /api/reviews/{id}/commitment-draft` is an operator/CSRF-protected advisory
derivation with an expected review revision. It reads immutable Git blobs, not
symlink targets or untracked files. `CommitmentAdvisor` uses the configured LLM
gateway to draft a statement, rationale, verification plan and at most two cited
risks. `POST /api/reviews/{id}/risk-analysis` provides the same analysis independently
of the editor, including on historical reviews. Neither endpoint mutates governed
review state; both persist version-bound `AIAdvisoryRun` records.

Context is limited to root README files, up to six changed paths, three discovered
test files, bounded base/target excerpts, recorded check summaries, and existing
commitments. Sensitive file paths are excluded; known credentials and common
secret assignments are redacted (not a guarantee that arbitrary source secrets
are detected). Total JSON is capped at 45,000 characters. Repository prose is
untrusted data, never instructions or executable commands. Requests go to the
operator-configured provider, so only use repositories authorized for that service.

Output must satisfy a strict typed schema and cite actual source/check IDs. Failed
requests or validation return an explicitly labelled local draft with no model
risk verdict. A citation proves reference existence, not semantic correctness:
model runs keep `grounded=false` and `semantic_support_unverified`. Provider,
model, prompt version, context hash, usage and latency are retained. Saving an
AI run atomically checks review and project versions. Model draft rationales link
back to the run and source identities; change-package exports include advisory
runs separately from evidence. Confirmation uses the ordinary commitment endpoint
and creates an unsatisfied evidence obligation; AI output never satisfies it.

OpenAI-compatible Chat Completions supports explicit base paths such as BigModel's
`/api/coding/paas/v4` without appending an extra `/v1`. A bare origin still defaults
to `/v1`. The existing Anthropic proxy path convention is unchanged. JSON repair
is bounded to one additional call; a repair still marked truncated is rejected.
Local credentials live in ignored `.env`, never browser JavaScript or reports.

`POST /api/reviews/{id}/revisions` creates a new review only from an exact
`rebase_required` predecessor and an unchanged project baseline. It resolves the
new target and runs the ordinary analysis, then carries requirements with new
obligation identities. Predecessor ID/revision, update reason, and historical
questions are persisted. Prior approvals, waivers, attestations, source readings,
realization IDs and round-trip results are not reused as current facts. The
selected intent remains linked, without rewriting its original realization.
Database insertion atomically rechecks predecessor and project versions and
rejects duplicate active revision pairs. Optional model fields preserve backwards
compatibility with existing review JSON.

## Runtime boundary

The default server binds to `127.0.0.1`. Non-loopback use requires TLS termination and secure cookies. Self-signup is opt-in and creates operator identities only; it does not create project authority. GitHub integration is remote-read/local-clone only; it does not push or administer repositories. This repository is not a hosted multi-tenant system and does not claim tenant isolation, SSO, MFA, distributed sessions, remote workers, or managed key custody.
