# AgenticConsensus

This repository is the public source of truth for the project and its official
website. Use `AgenticConsensus` as the public project name. The Python package,
CLI, internal namespaces and existing environment variables retain
`agentic-consensus` / `AGENTIC_CONSENSUS` for compatibility.

- Maintain the website in `website/` on `main`. Do not maintain the retired
  personal-site copy or a separate website branch.
- Keep README concise; put detailed operator documentation in `docs/usage.md`.
- Do not commit credentials, local data, database files, browser state,
  private repositories, or private development/QA records.
- Keep model output advisory. Evidence, authority and human decisions must
  retain their server-side validation and provenance.
- Use synthetic data in examples. Describe the project's current scope
  without implying a completed user study or general security guarantee.

Verify application changes with the relevant Python and Node tests.
Verify website changes in a browser at desktop and mobile widths, including
language switching, links, keyboard navigation and reduced-motion behavior.

```sh
.venv/bin/python -m pytest
node --test tests/*.test.cjs
.venv/bin/python -m build
```
