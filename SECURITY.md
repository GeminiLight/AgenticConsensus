# Security policy

## Supported version

Security fixes are applied to the current `0.22.x` development line. Older snapshots are research artifacts and are not maintained as supported releases.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting or open a private security advisory for this repository. Do not file a public issue for authentication bypasses, secret exposure, path traversal, unsafe Git execution, evidence or audit tampering, authority escalation, signature verification failures, or destructive recovery behavior.

Include the affected version, a minimal synthetic reproduction, the expected security invariant, and the observed result. Remove credentials, private repository content, local paths, session cookies, API keys, database files, and unredacted audit exports.

## Deployment boundary

AgenticConsensus is local-first software. Its default loopback bind is part of the security model. A non-loopback service requires operator-managed TLS and `--secure-cookies`; the application does not itself provide tenant isolation, SSO, MFA, distributed rate limiting, or a managed trust service.

Development authentication (`admin/admin`) is allowed only on loopback and must never be used for a shared instance. Self-signup is disabled by default. An explicitly opted-in preview may create operator identities, but registration never creates an administrator or a project authority grant. Model output is advisory and is never accepted as evidence, authority, or a governance decision.

GitHub access uses a least-privilege GitHub App with Metadata and Contents read permissions. First-use App Manifest setup is administrator-only, CSRF-protected, bound to a one-time hashed state, and completed without a local callback cookie. The generated client secret is encrypted; the unused private key and webhook secret are discarded. OAuth state is independently one-time and PKCE-bound; access and refresh tokens are encrypted locally and are never returned by the API. Clone credentials are supplied through a short-lived askpass environment and are not embedded in process arguments or persisted remotes. The clone host is pinned to `github.com` or the configured GitHub Enterprise host so untrusted repository metadata cannot redirect a token. The integration has no remote write, merge, deletion, pull-request, or administration operation. Protect the database, optional deployment `.env`, credential-encryption key, and managed private-repository clones as one sensitive operator-owned runtime set.
