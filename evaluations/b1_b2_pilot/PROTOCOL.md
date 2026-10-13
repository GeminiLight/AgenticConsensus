# B1/B2 Exploratory Model Pilot Protocol

## Purpose

This pilot checks whether the information-matched manipulation, response schema, scoring code, and relational review surface can run end to end. It is not a human-subject study and is not confirmatory evidence that B2 improves developer decisions.

## Frozen design

- Six seeded coding-governance cases.
- Conditions: B1 chronological decision ledger and B2 relational project-state review.
- Both conditions are generated from the same canonical atomic fact objects. Fact IDs, payloads, counts, and inventory SHA-256 must match exactly.
- B2 may add typed traversal, computed conflict/coverage indices, and an atomic gate, but these are derived only from fact IDs already present in both conditions.
- The same model, system prompt, output schema, provider-default sampling policy, maximum output tokens, timeout, case order, and repetition count are used for both conditions. The client does not send a `temperature` field because the configured OpenAI Responses-compatible gateway does not accept it. These runtime limits are frozen in the run manifest.
- Condition order alternates by case and repetition. The raw order is preserved.

## Outcomes

1. Violation identification: fact-ID precision, recall, F1, and exact set match.
2. Evidence adequacy: exact match of adequate or inadequate.
3. Policy-compatible disposition: exact match among commit, rebase, reject, waive_then_commit, and escalate_authority.
4. Authorization compliance: exact match of compliant or noncompliant.

The exploratory aggregate reports each dimension separately and the fraction of trials correct on all four. Latency, token usage, invalid responses, and API failures are reported as costs or coverage limits.

## Interpretation boundary

No significance test or causal claim is made from this pilot. Repeated calls to one model are not independent human participants. A later preregistered study must use human reviewers, counterbalanced task assignment, validated workload measures, and construction/correction cost accounting.
