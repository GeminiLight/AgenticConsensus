# Contributing to AgenticConsensus

AgenticConsensus treats evidence, authority, and auditability as product contracts. A change is complete only when its user-visible behavior and governance boundary are both verified.

## Local setup

```bash
git clone https://github.com/GeminiLight/AgenticConsensus.git
cd AgenticConsensus
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest
```

Create a synthetic scenario and run the local console:

```bash
.venv/bin/agentic-consensus demo --reset
.venv/bin/agentic-consensus serve
```

Never commit `.env`, `var/`, browser state, local databases, recovery snapshots, API keys, or real repository content.

## Change workflow

1. Write a failing test for changed behavior or a regression.
2. Implement the smallest coherent change.
3. Run the relevant tests, then the full suite.
4. For interface changes, exercise the real browser at desktop, 390px mobile, keyboard-only, failure/fallback, and paper-view states.
5. Explain effects on evidence admission, authority, decisions, provenance, authentication, backup, or recovery in the pull request.

Do not weaken server-side checks merely to unblock the interface. Global product roles and project authority grants must remain separate. Model output must remain advisory.

## Interface acceptance

- The current change, evidence status, and next valid action are visible before secondary configuration.
- All critical mobile controls have at least a 44px target.
- Loading, failure, retry, blocked, and empty states remain in context.
- Contract Graph facts remain available through the relation table if Canvas rendering is unavailable.
- Paper view omits account identity and local repository paths.
- There are no new console errors, failed requests, or horizontal page overflow.

## Pull requests

Keep pull requests focused and use synthetic data in screenshots. Include the commands you ran and the exact outcome. Security-sensitive findings belong in a private security advisory, not a public issue.
