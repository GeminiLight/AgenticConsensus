# AgenticConsensus

AgenticConsensus is a local-first merge-decision workspace for pull requests proposed by coding agents. A reviewer selects an open GitHub pull request and gets a concise decision brief before opening the underlying evidence. The product turns that PR snapshot into an auditable review package containing:

- the original language request, context version, competing structural interpretations, uncertainties, clarification history, selection, and provenance;
- a declared base project-state version;
- explicit claim, artifact, and evidence deltas ($\Delta C$, $\Delta A$, and $\Delta E$);
- deterministic evidence from Git, Python AST analysis, policy checks, and tests, with outcome, provenance, artifact version, and freshness;
- claim-level evidence obligations frozen into each review, with explicit satisfied, waived, missing, contested, or stale coverage;
- unresolved or unobservable risks;
- governed evidence admission plus an explicit human decision: commit, waive, rebase, reject, or rollback;
- a versioned attestation-root registry with authorized add, revoke, and atomic rotate transitions.

For its first executable synchronization path, the selected structural change is a single Python `from`-import substitution. The realization operator creates a candidate commit in an isolated Git worktree and stores it under `refs/agentic-consensus/proposals/*`; it never rewrites the caller worktree. An independent AST pass rehydrates candidate structural deltas from the resulting diff, then records round-trip discrepancy, observable coverage, and explicit unobservable state before creating the linked review.

The language model is deliberately bounded. It can answer questions over one review, propose competing intent interpretations, surface evidence gaps, and run a proposer/critic/synthesizer pass. Every factual review answer must resolve to canonical evidence-card IDs. It cannot mark evidence as passed, attach evidence, select an interpretation, or authorize a decision.



The interface follows the decision task instead of presenting one undifferentiated graph: reviews open with a Decision brief, Changes focuses on one file, and Evidence separates outstanding requirements from records and claim observations. The Audit graph offers evidence coverage and decision-trail lenses; paper view shows the full contract. Search isolates an immediate control path, and the relation table remains available to keyboard users and when Canvas rendering is unavailable.

Within the current session, returning from Project or Rules restores the selected
review and its section for that project. Changes, Evidence and Audit each offer
**Back to decision**. A blocking check disables approval while leaving **Request
update** and **Reject** available to operators; the decision area also shows the
governing authority or rollback consequence. **AI risk analysis** opens on demand
and identifies unavailable model analysis explicitly. The commitment Canvas keeps
its file reader independently scrollable on desktop, with **Focus reading** for a
wider source view; narrow screens use normal page scrolling.

The Canvas places the selected commitment's evidence status beside the whole
review's approval status. Supporting evidence for one commitment cannot clear a
blocker elsewhere. If a commitment has several verification requirements, the
summary counts the supported requirements and prioritizes unresolved ones;
waivers remain exceptions rather than supporting evidence. **Review required
evidence** opens the relevant requirement and its verification plan directly.
Changes to an agreed statement also expose the previous statement on demand.

For a new review without commitments, **Define what must hold** drafts a requirement
from the request and source. The editor leads with the requirement and verification
plan; the original request, rationale and sources remain expandable. Passing tests
alone do not fill that requirement. After approval, **View agreed commitment** opens
the accepted requirement on the Canvas when it still matches the project version.

Decision keeps the current outcome and available actions first. Revision history,
commitment details and verification plans expand in place; deep links open the
relevant commitment automatically. Changes holds the file map, while Audit holds
request-to-decision links. The Canvas uses compact rows for files without an authored
reading, and the reader keeps the selected path and source controls together. A
completed Request leads with **Open linked review**, with interpretation history
and implementation checks available below as expandable details.

The Rules view keeps each claim compact until expanded. Its detail shows the current
configured evidence requirements, accepted sources and waiver boundaries, then
links to reviews that actually reference the claim. Review requirements are frozen
snapshots, not inferred from the current claim status. **Inspect evidence** opens
the selected review’s coverage; **Back to governing claim** restores the inspected
rule. These controls are read-only and do not change evidence or record decisions.

## Product boundary

Version 0.22.3 is a verifiable, recoverable, authenticated local multi-user product for a technical lead reviewing agent-generated pull requests. Its primary path is GitHub-first: choose a repository, choose an open PR, and receive a merge-readiness brief with coverage, top risks, missing evidence, and the next human action. Every blocking check carries the action that resolves it, the diff renders per file with findings anchored to the lines they concern, and an evidence-grounded assistant answers questions without any authority to decide. It also preserves language-mediated intent as versioned candidate structural changes, records clarification and explicit selection, and supports one bounded round-trip path from a Python import substitution to an isolated Git proposal and back to an independently rehydrated structural delta. Passwords use Argon2id. Opaque sessions remain server-side, are delivered in `HttpOnly` and `SameSite=Strict` cookies, expire after eight hours, and require a synchronizer CSRF token for mutations. Global administrator, operator, and viewer roles control console capabilities. The authenticated audit identity is bound at the server boundary to every governed human action, while project authority grants independently decide which identities may attest, waive, commit, or manage trust.

Every administrator-created identity starts with a temporary password and cannot open project data until it is replaced. Self-service password change verifies the current credential, rotates the current session, and revokes every other session. Administrators can reset another identity to a new temporary password, which revokes its sessions and forces another change. Users can also revoke all other sessions without changing the current password. Password and session lifecycle operations append credential-free identity audit events.

If no administrator can sign in, a local host operator can stop the console and run the offline `recover-password` command. Recovery accepts the temporary password only through a hidden terminal prompt or a named environment variable, acquires an exclusive database lock, validates the live state, writes a verified pre-change backup, revokes every target session, forces password replacement at the next login, and appends the operator label and reason without the credential. This is host-level maintenance, not remote identity proofing.

Project claims may require authorized human records or DSSE-wrapped SLSA Verification Summary Attestations signed by project-pinned Ed25519 keys. Trust-root changes require purpose-bound key possession proof and version-checked authorization. Decision, trust, and identity events remain separate append-only records, and verified backups validate all persisted authentication and governance links.

This is not a hosted multi-tenant service. It does not yet provide tenant isolation, SSO/OIDC, MFA, out-of-band self-service recovery, breached-password screening, API tokens, distributed sessions or rate limiting, remote job workers, organization-wide policy administration, or managed KMS/Sigstore trust. Keep it on localhost unless it is placed behind an operator-managed TLS boundary.

## Quick start

```bash
git clone https://github.com/GeminiLight/AgenticConsensus.git
cd AgenticConsensus
uv venv .venv
uv pip install --python .venv/bin/python -e '.[dev]'
.venv/bin/agentic-consensus demo --reset
.venv/bin/agentic-consensus serve
```

Open `http://127.0.0.1:8765`. The seeded repository models a task-scoped capability migration. Its tests pass, but a connector selects its credential provider dynamically; static analysis cannot establish the governed relation, and the only broad-token runtime trace belongs to the older artifact version. The Reviewer therefore sees an inconclusive observation, stale evidence, and a blocked commit rather than a false pass.

By default, mutable data and `.env` are resolved from the directory where the command is run. Set `AGENTIC_CONSENSUS_HOME` to an operator-owned absolute directory when the service is launched from another location or by a service manager.

### Reopen an existing workspace

From the same project folder, run `.venv/bin/agentic-consensus serve` and keep the
terminal open. Visit [the local app](http://127.0.0.1:8765/) in your browser; do not
open `system/web/static/index.html` as the application. That file now shows a
launch guide because project data and sign-in require the running service.
If you selected another port, use the address printed in your terminal.

Sign in with the account created for this installation. An existing workspace
does not need to be installed or seeded again; `demo --reset` is for rebuilding
the demo, not for starting the app. If an app resource fails to load, use **Try
again** on the startup screen after restoring the connection.

### Connect a GitHub account

The repository intake dialog supports either an existing local Git checkout or a repository selected through a GitHub App. The primary path lists open pull requests, fetches the selected base and head revisions into an operator-owned managed checkout, and opens the decision brief in one action. Both repository and PR metadata are revalidated on the server, and the fetched revisions must match the GitHub response. The GitHub boundary is read-only: the product does not push, delete, merge, create a pull request, or change repository settings. Disconnecting removes the local authorization while preserving already imported governance projects.

Open **Account → GitHub repositories** and click **Connect GitHub**. On the first use of a self-hosted instance, an administrator is sent through GitHub's App Manifest page; GitHub creates the preconfigured connector, then the same browser flow continues through account authorization and repository installation. Later operators start directly at GitHub authorization. Ordinary users never enter a client ID, client secret, app slug, or environment variable.

The generated App is installable by additional accounts but requests only repository **Metadata: read**, **Contents: read**, and **Pull requests: read**, subscribes to no events, and disables webhook delivery. The returned client secret is encrypted locally; the unused private key and webhook secret are discarded. The browser authorization step uses PKCE and a one-time, ten-minute state. User and refresh tokens use the same mode-`0600` local encryption-key boundary. Git receives the token through a temporary `GIT_ASKPASS` process environment; neither the command arguments nor the persisted `origin` URL contains credentials. Advanced centrally managed deployments may override the generated App through the variables documented in `.env.example`; this is not part of the user login flow.

On first run, create the administrator in the browser and confirm the password. The audit identity must exactly match an identity named in the project authority grants. The seeded C44 workspace uses `security-lead@example.test`. The service binds to localhost by default. Runtime data is written under `var/` and never sent to a model unless model summarization is explicitly enabled.

For local test and development only, the console can bootstrap a known administrator with username `admin`, password `admin`, and an explicitly supplied audit identity:

```bash
agentic-consensus serve \
  --development-auth \
  --development-audit-identity developer@example.test
```

This mode is rejected for every non-loopback host, does not weaken the normal browser bootstrap or user-management password policy, and only creates the identity when the authentication database is empty. Do not use it for a shared or deployed instance.

## Authentication and access control

- **Administrator** can inspect and mutate governed state, create or disable local identities, and read the identity audit stream.
- **Operator** can inspect and mutate governed state but cannot administer identities.
- **Viewer** has read-only access. Direct mutation requests are rejected by the server even if the interface is bypassed.

These roles grant product access, not project authority. A global administrator still needs a matching project authority grant for `attest`, `commit`, `waive`, `rebase`, `reject`, `rollback`, or `manage_trust`.

To delegate an existing project authority to a registered, active local identity, stop the console and run the offline command below. The named authorizer must already hold `manage_trust` in the project's default authority grant. The command requires the exact project version, advances it once, copies only that grant's actions, and appends an `authority_actor_add` project event.

```bash
agentic-consensus grant-authority-actor \
  --project PROJECT \
  --authorizer EXISTING_AUTHORIZER \
  --actor REGISTERED_AUDIT_IDENTITY \
  --reason "Authorize this identity for the governed local workflow" \
  --expected-version N
```

Use **Password** to change the current credential or sign out other sessions. Administrator-created identities must replace their temporary password at first sign-in. In **Users**, an administrator can reset another active identity; this revokes its sessions and restores the forced-change gate. Password resets and changes are never written to audit payloads.

The default command only accepts a loopback bind. A non-loopback host requires `--secure-cookies` and should be used only behind TLS:

```bash
agentic-consensus serve --host 0.0.0.0 --secure-cookies
```

In secure-cookie mode the service uses a `__Host-` session cookie and emits HSTS. Browser responses also disable framing and MIME sniffing, use a restrictive Content Security Policy, suppress referrer disclosure, and mark HTML/API responses `no-store`.

## Reviewer workflow

1. Choose a GitHub repository and an open pull request. The product imports a read-only snapshot and opens its merge-decision brief automatically. For a local checkout, use **Compare revisions** and supply the immutable base and target refs.
2. In **Requests**, preserve the original request with at least two candidate structural interpretations. Clarify open questions, edit a saved proposal or add an alternative with a recorded reason. Compare versioned changes in **Decision trail**, then explicitly select one candidate. Editing never selects or executes it.
3. For a supported import substitution, run **Realize with Phi**. The service checks the exact base, works in an isolated Git worktree, stores a proposal commit under a dedicated ref, rehydrates the diff with Psi, computes $D_{\mathrm{rt}}$ and observable coverage, and opens the linked review. Failed preconditions are recorded without creating a review or changing the caller workspace.
4. Alternatively, create a review package from an externally produced target revision with a concrete change intent, proposer, immutable base revision, and target revision.
5. Inspect the package $\langle v^t,\Delta C,\Delta A,\Delta E,U,W\rangle$, including intent and realization linkage, rehydrated claim observations, frozen evidence obligations, artifact anchors, evidence lifecycle, stale records, overlaps, and admission checks.
6. Inspect the **Contract Graph** to trace intent, interpretation, realization, rehydration, version state, proposal, artifacts, claims, evidence, findings, authority, and decisions as one semantic relation map. Use **Relation table** for the keyboard-accessible view, **Focus graph** for focused analysis, and **Download SVG** for a deterministic reviewer-safe figure.
7. Open **Assistant** in the right inspector and ask about the selected review. **Answer options** can add an independent challenge and synthesis when a model is configured. **Find recorded gaps** is a separate local action: it lists next checks but does not run them. Inspect source records before using any advice. Questions and unsaved answer edits stay with their review during this signed-in page session; saved answers are version-checked and never confer approval authority.
8. Inspect the attestation-root registry. An authorized trust administrator can add a proven key, revoke an active key, or rotate to a proven replacement. Every operation advances the project version and appends a project audit event.
9. Attach an authorized human record or import a signed VSA for a declared obligation. Human evidence is server-bound to the review target. Signed evidence must pass DSSE Ed25519 verification and match an active, in-window root, the configured verifier, target commit, resource URI, authority, and verified level.
10. Load the unified diff or download the reviewer-safe JSON package. The server-backed export omits the local repository path and includes both review and project audit timelines.
11. Record an authorized commit, bounded waiver, rebase request, rejection, or rollback. A waiver may target findings or explicitly waivable evidence obligations. Commit remains disabled while admission blockers are open.

The console starts in **Light theme** and lets the operator switch directly between Light and Dark. The preference is stored only in browser local storage and is applied by a same-origin bootstrap before the main stylesheet, so it survives refresh without violating the console Content Security Policy.

Use `http://127.0.0.1:8765/?paper=1` for the blue, light, reviewer-safe paper projection. It uses the same API data as the operator workspace, hides runtime account and proposer identity, and is not a mock view.

The interactive graph renderer is Cytoscape.js 3.34.2, vendored under `system/web/static/vendor/` with its MIT license. The browser never loads a graph library from a CDN. `/api/reviews/{review_id}/graph` is the authoritative, versioned graph projection; the Canvas view, accessible relation table, and SVG export all consume that same payload.

## CLI

```bash
agentic-consensus serve                     # local web console
agentic-consensus demo --reset               # create a synthetic Git scenario
agentic-consensus analyze --project PROJECT  # analyze a project review
agentic-consensus grant-trust-admin --project PROJECT --actor ACTOR --reason REASON --expected-version N  # offline v0.6 upgrade
agentic-consensus grant-authority-actor --project PROJECT --authorizer AUTHORIZER --actor ACTOR --reason REASON --expected-version N  # offline audited delegation
agentic-consensus sign-trust-proof --template PACKAGE.json --private-key KEY.pem --output PROOF.json  # offline signer
agentic-consensus backup --output BACKUP.db  # verified online snapshot + manifest
agentic-consensus restore --input BACKUP.db  # offline verified restore + recovery copy
agentic-consensus recover-password --username USER --operator HOST_OPERATOR --reason REASON  # offline local recovery
agentic-consensus-check                      # configuration and database health
```

## Backup, restore, and local credential recovery

Create a consistent snapshot while the console is running:

```bash
agentic-consensus backup --output backups/agentic-consensus.db
```

The command writes the SQLite snapshot and `agentic-consensus.db.manifest.json`. The manifest records its SHA-256 digest, byte size, timestamp, and validated project, review, review-event, and project-event counts. Snapshot validation also checks authentication identities, sessions, identity-audit events, normalization rules, credential shape, and record ownership when those tables are present. Existing backup files are not overwritten unless `--overwrite` is explicit.

Stop the console before recovery, then restore from the verified snapshot:

```bash
agentic-consensus restore --input backups/agentic-consensus.db
```

Restore verifies the manifest digest, SQLite integrity, every persisted Pydantic model, and project-review-event ownership links before changing the live database. It first saves the current database beside the live file as `agentic-consensus.pre-restore-<timestamp>.db` with its own manifest. A healthy current database is retained as a validated backup. A corrupt current database is retained byte-for-byte as a raw recovery artifact, including any WAL or SHM sidecars and their digests, before the verified snapshot is installed. If the console still holds the database, restore exits without mutation.

If every administrator credential is unavailable, stop the console and run:

```bash
agentic-consensus recover-password \
  --username USERNAME \
  --operator LOCAL_HOST_OPERATOR \
  --reason "Recover local administrator access"
```

The command prompts twice without echo. For non-interactive maintenance, add `--password-env VARIABLE_NAME`; the variable value is never printed or persisted. Recovery refuses a live console, an unknown or disabled identity, an unchanged or invalid password, and any invalid database. A successful operation creates `*.pre-password-recovery-*.db` plus its manifest before changing the password. Keep that snapshot protected because it contains the previous authentication state.

## AI Copilot and model configuration

The advisory gateway supports OpenAI's Responses API (the default OpenAI mode), OpenAI-compatible Chat Completions gateways, and Anthropic's Messages API. Secrets are read only from environment variables and are never persisted.

The console exposes five bounded AI capabilities:

- **Review assistant** answers only from a canonical context made of review, claim, evidence, finding, obligation, admission-check, decision, and bounded-diff cards. Unknown citation IDs fail closed to a deterministic answer. The inspector discloses local versus configured-provider processing, links sources to existing records, and separates human-kept edits from the original answer. Citation-ID matching does not establish semantic correctness.
- **Intent interpreter** creates at least two distinct structural candidates plus uncertainties and clarification questions. It does not save, select, or realize an Intent Map.
- **Evidence-gap planner** deterministically maps missing, stale, contested, and inconclusive records to exact next checks.
- **Critic and synthesizer** use separate calls when the operator enables deliberation. If any stage fails structure or citation validation, the complete deliberation is discarded instead of presenting a partial proposal as a synthesis.
- **Feedback and evals** persist accepted, edited, or rejected advice and report verified grounding, citation-ID precision, a conservative mechanical faithfulness proxy, fallback rate, latency, token use, and acceptance rate. Model answers with resolved IDs remain marked semantically unverified until an independent support check exists.

When test evidence is missing, an operator can run the project command against the immutable review target. An existing project command is fixed during the review and cannot be replaced there. If intake left it empty, a one-time command may repair that review; the exact command is recorded in the review audit event and does not silently rewrite project configuration.

AI runs and feedback live in separate SQLite tables. They do not increment project/review revisions and do not append governed decision or evidence events. Operators can invoke model-backed actions; viewers can inspect existing runs and aggregate evals. Enabling a remote provider sends a bounded review context to that provider, so keep the model disabled for repositories that must remain entirely local.

The CLI automatically loads `.env` from the project root without overriding variables already supplied by the shell or service manager. Copy `.env.example` to `.env`, fill only the provider you use, set `CONSENSUS_LLM_ENABLED=true`, and restart the service. The local file is excluded by `.gitignore`; keep its permissions restricted and never commit or share it.

For OpenAI Responses:

```bash
export CONSENSUS_LLM_ENABLED=true
export CONSENSUS_LLM_PROVIDER=openai_responses
export OPENAI_API_KEY=...
export OPENAI_MODEL=gpt-5
# Optional for an OpenAI-compatible gateway:
export OPENAI_BASE_URL=https://api.openai.com/v1
```

For a gateway that only exposes Chat Completions, set `CONSENSUS_LLM_PROVIDER=openai_chat`. OpenAI modes request strict JSON Schema output by default. Non-OpenAI compatible gateways also receive the schema in the instruction because some ignore `response_format`; one non-JSON result may be repaired through a single bounded second call. Gateways with older structured-output support can set `CONSENSUS_LLM_STRUCTURED_OUTPUT=json_object`, or use `none` as a last compatibility fallback. The default Chat Completions request uses `max_completion_tokens`; older gateways can opt into `OPENAI_CHAT_MAX_TOKENS_FIELD=max_tokens`. Reasoning gateways that expose an OpenAI-compatible `thinking` extension can set `OPENAI_CHAT_THINKING=enabled` or `disabled`; leave it unset for standard OpenAI endpoints.

Anthropic remains available with `CONSENSUS_LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY` (or `ANTHROPIC_AUTH_TOKEN`), `ANTHROPIC_MODEL`, and optional `ANTHROPIC_BASE_URL`.

When no provider is explicit, a configured `OPENAI_API_KEY` plus `OPENAI_MODEL` selects Responses; otherwise Anthropic is selected. Optional OpenAI headers use `OPENAI_ORGANIZATION` and `OPENAI_PROJECT`. Without `CONSENSUS_LLM_ENABLED=true`, the product keeps Review Q&A, Intent drafts, summaries, and gap planning available through conservative deterministic fallbacks. Model output remains advisory in every mode.

## Information-matched B1/B2 pilot

The exploratory pilot under `evaluations/b1_b2_pilot/` generates a chronological B1 ledger and relational B2 review view from the same canonical atomic fact objects. Its dry run verifies that each case has identical fact IDs, payloads, counts, and inventory hashes before any model call:

```bash
.venv/bin/python -m evaluations.b1_b2_pilot.pilot \
  --dry-run \
  --output evaluations/b1_b2_pilot/runs/preflight
```

With the OpenAI Responses-compatible provider configured, run a new model batch in an empty output directory:

```bash
CONSENSUS_LLM_TIMEOUT=60 CONSENSUS_LLM_MAX_TOKENS=1200 \
  .venv/bin/python -m evaluations.b1_b2_pilot.pilot \
  --repetitions 2 \
  --output evaluations/b1_b2_pilot/runs/my-run
```

The run freezes hashes, model, sampling policy, output budget, timeout, case order, repetitions, and the four decision dimensions. It writes every valid response and failure before producing separate B1/B2 aggregates. The `runs/` directory is local and Git-ignored because raw provider output is operational evidence, not release source. This model pilot tests the manipulation and measurement path; it is not a human study or evidence of a causal treatment effect.

## Signed CI attestations

During project registration, an operator may pin an Ed25519 public key, its key ID, the verifier URI it represents, and a resource URI prefix. The corresponding claim obligation selects `dsse_ed25519` verification and names a required VSA level. The demo command generates a one-time signed envelope and prints its path; the private key is discarded and is never stored.

Import accepts a DSSE JSON envelope using `application/vnd.in-toto+json` or a predicate-specific in-toto JSON media type. Verification checks the DSSE pre-authentication encoding and at least one signature from a pinned key before parsing JSON. It then enforces:

- in-toto Statement v1;
- SLSA Verification Summary Attestation v1;
- `subject.digest.gitCommit` equal to the immutable review target;
- the signer key, `verifier.id`, and project authority binding;
- exact `resourceUri` formed from the pinned prefix and target commit;
- `verificationResult` equal to `PASSED`;
- every level required by the selected obligations.

Malformed base64, duplicate JSON keys, non-standard JSON constants, tampering, untrusted keys, failed results, wrong subjects, authority mismatches, and repeated envelopes fail closed. The complete verified envelope and its SHA-256 identifier are retained in the evidence record for independent re-verification. The implementation follows the [in-toto envelope](https://github.com/in-toto/attestation/blob/main/spec/v1/envelope.md), [in-toto Statement](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md), and [SLSA VSA](https://slsa.dev/spec/v1.2/verification_summary) contracts.

## Trust-root lifecycle

The registry keeps every key ID and public key permanently unique within a project, including revoked entries. A new root is accepted only while its declared validity window is active and after a DSSE VSA signed by that new key proves possession against the current governed head. The proof must use policy `https://agentic-consensus.local/policies/trust-root-possession/v1` and include `CONSENSUS_TRUST_ROOT_POSSESSION_V1`; an ordinary source or build VSA is rejected even when its signature is valid. In the trust dialog, **Build signing template** creates the exact payload, envelope placeholder, and base64 DSSE PAE signing input. **Download signing package** saves that complete contract for an isolated signing environment. Run `agentic-consensus sign-trust-proof --template PACKAGE.json --private-key KEY.pem --output PROOF.json`, then upload `PROOF.json`. The signer accepts unencrypted PKCS8 PEM or an encrypted PEM whose password is read from a named environment variable with `--password-env`; it verifies the package purpose, canonical bytes, and private-to-public-key match before signing. It never overwrites an output file. The console never receives the private key. `Rotate` combines replacement proof, old-key revocation, and new-key admission in one atomic project transition. `Revoke` supports two modes:

- **Prospective** retains evidence already admitted under the key but rejects every later import.
- **Retroactive** additionally makes prior evidence from the key stale. Both the browser and the server require explicit destructive confirmation.

Trust changes require an exact project version, the governing policy, the default project authority, a substantive reason, and an identity holding `manage_trust`. Existing v0.6 projects deliberately do not receive that new privilege automatically. Stop the console and run the explicit `grant-trust-admin` command for an identity that already holds `commit` authority; the upgrade advances the project version and appends an `authority_grant_extend` event.

## Safety defaults

- Repository paths are explicitly registered and resolved before use.
- Git commands use argument arrays, validated refs, timeouts, and no shell.
- Test execution is disabled unless a project has an allowlisted command.
- `commit` is blocked on stale bases, failed/missing evidence, unresolved critical findings, and unsatisfied evidence obligations.
- Authorized-record admission requires an identified recorder, matching policy and authority, an `attest` grant, explicit obligation IDs, a substantive summary, and provenance. The artifact reference is set by the server.
- DSSE admission verifies a pinned Ed25519 signature before parsing, then validates the in-toto subject and SLSA VSA policy contract. Human records cannot satisfy DSSE-only obligations.
- Trust-root add and rotate require a purpose-bound new-key possession proof with the dedicated policy URI and verified level. A machine-signable template is available without exposing private-key material. Key IDs and public-key material cannot be reused under aliases.
- Trust-root changes require `manage_trust`, exact project-version concurrency control, a named actor, governing policy, authority, and rationale. Retroactive revocation additionally requires explicit server-side confirmation.
- Revoked, expired, and not-yet-valid roots cannot admit new evidence. A scheduled future root can still be cancelled before it becomes trusted.
- Waivers require an identified human, reason, scope, and expiry. Expired finding and obligation waivers cease to satisfy admission and can be renewed without overwriting history.
- Configured policy grants are enforced at the server boundary for attest, commit, waiver, rebase, rejection, and rollback.
- Governed human actors are taken from the authenticated server session; a request cannot attribute an action to another identity.
- Administrator, operator, and viewer roles are enforced server-side. Identity creation and disable/enable operations are append-only audited, and disabling an account revokes its sessions.
- Passwords are stored only as Argon2id hashes. Session cookies are opaque, `HttpOnly`, `SameSite=Strict`, and paired with a synchronizer CSRF token. Authentication and API responses use `no-store`.
- The first administrator is created in one exclusive transaction, and the current or last active administrator cannot be disabled.
- Administrator-created identities are blocked from project data until their temporary password is replaced. Password change requires the current credential, rotates the session, and revokes all other sessions.
- Administrator resets cannot target the current account, revoke every target session, require another password change, and append no credential material to the identity audit.
- Login throttling uses independent per-username and per-client windows so targeted guessing and username spraying do not bypass one another. The local limiter remains in-process and resets on restart.
- Every decision carries policy, authority, actor, rationale, and provenance in a separate record.
- Project, review, trust-root, and audit-event writes form version-checked SQLite transactions.
- Reviewer exports are generated server-side, use `no-store`, and omit the registered local path.
- Provenance-prefix checks on authorized human records remain declarative source constraints. DSSE-only obligations use cryptographic verification and cannot be satisfied through that path.
- Database health checks validate SQLite integrity, persisted model shape, and ownership links rather than reporting row counts alone.
- Offline password recovery requires exclusive database ownership, a verified pre-change snapshot, a named host operator, and a substantive reason; it revokes every target session and forces normal password replacement before project access.
- Durable policy or agent-profile changes remain proposal-only, except for the narrow offline trust-admin upgrade used to migrate an existing decision owner. That command also requires exclusive database ownership.

## Development and license

See [CONTRIBUTING.md](../CONTRIBUTING.md) for the test-first workflow and browser acceptance checks, [docs/architecture.md](architecture.md) for the trust boundaries, and [docs/user-journeys.md](user-journeys.md) for the product experience contract.

AgenticConsensus is licensed under Apache-2.0. Cytoscape.js is vendored under its MIT license; see [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).
