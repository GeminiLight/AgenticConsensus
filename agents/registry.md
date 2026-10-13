# Agent registry

| Agent | Mechanism | Authority |
|---|---|---|
| proposal-interpreter | bounded model or deterministic fallback | advisory |
| change-auditor | Git, AST, policy rules, tests | deterministic evidence |
| evidence-summarizer | bounded model or deterministic fallback | advisory |

No agent may approve or execute a human-gated decision.
