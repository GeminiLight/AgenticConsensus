# AgenticConsensus

A shared, versioned project state for human–AI coding collaboration.

AgenticConsensus connects a change request, its interpretation, code changes,
requirements, evidence, and an authorized human decision. It helps a reviewer
inspect what changed, which requirements are covered, and what still needs checking.

**[Website](https://tianfuwang.tech/AgenticConsensus/)** ·
**[Getting started](docs/usage.md)** ·
**[Architecture](docs/architecture.md)**

## What it does

- Reviews immutable Git revisions or a read-only snapshot of a GitHub pull request.
- Tracks requirements across revisions and keeps evidence bound to the version it checks.
- Presents code, evidence coverage, open risks, and a connected audit graph.
- Records authorized human decisions with version checks and an audit trail.
- Offers optional evidence-grounded model advice. Model output cannot approve a change.

This is an early, local-first research prototype. Source analysis currently
focuses on Python imports; automated realization supports a bounded Python
import substitution. A recorded decision does not merge a GitHub pull request.

## Run locally

Requires Python 3.11+ and Git. No model key is needed for the core demo.

```sh
git clone https://github.com/GeminiLight/AgenticConsensus.git
cd AgenticConsensus
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/agentic-consensus demo --reset
.venv/bin/agentic-consensus serve
```

Open **http://127.0.0.1:8765** and create the first administrator account.
For the seeded demo, use `security-lead@example.test` as the audit identity so
it matches the synthetic project's authority grants. To reopen the workspace,
run `serve` again; `demo --reset` rebuilds the demo data.

The demo illustrates a change whose tests pass while a governed architectural
relation remains unverified. Inspect its evidence and blockers before recording
a decision. Optional model configuration is documented in [.env.example](.env.example).

Runtime data stays in the local `var/` directory. Use the default localhost
address; see [SECURITY.md](SECURITY.md) for the deployment boundary.

## Development and website

```sh
.venv/bin/python -m pytest
node --test tests/*.test.cjs
.venv/bin/python -m build
```

The official website lives in **[website/](website/)** in this repository.
Changes to that directory on `main` publish through GitHub Pages. See
[website/README.md](website/README.md) for preview and maintenance instructions.

See [CONTRIBUTING.md](CONTRIBUTING.md) for contributions and
[docs/usage.md](docs/usage.md) for the full workflow.

Licensed under **Apache-2.0**. See [LICENSE](LICENSE) and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
