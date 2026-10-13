from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field

from system.services.llm import LLMConfig, OPENAI_RESPONSES_PROVIDER


PILOT_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "violation_fact_ids": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 30,
        },
        "evidence_adequacy": {"type": "string", "enum": ["adequate", "inadequate"]},
        "disposition": {
            "type": "string",
            "enum": ["commit", "rebase", "reject", "waive_then_commit", "escalate_authority"],
        },
        "authorization_compliance": {
            "type": "string",
            "enum": ["compliant", "noncompliant"],
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "rationale": {"type": "string", "minLength": 4, "maxLength": 2000},
    },
    "required": [
        "violation_fact_ids",
        "evidence_adequacy",
        "disposition",
        "authorization_compliance",
        "confidence",
        "rationale",
    ],
    "additionalProperties": False,
}


class PilotDecision(BaseModel):
    violation_fact_ids: list[str] = Field(default_factory=list, max_length=30)
    evidence_adequacy: str
    disposition: str
    authorization_compliance: str
    confidence: float = Field(ge=0, le=1)
    rationale: str = Field(min_length=4, max_length=2000)


class PilotModelError(RuntimeError):
    """A model failure with bounded, credential-free evidence for the trial log."""

    def __init__(
        self,
        message: str,
        *,
        failure_stage: str,
        upstream_error_type: str | None = None,
        raw_text: str | None = None,
        provider_status: str | None = None,
        incomplete_details: dict[str, Any] | None = None,
        http_status: int | None = None,
        provider_body: str | None = None,
    ):
        super().__init__(message)
        self.failure_stage = failure_stage
        self.upstream_error_type = upstream_error_type
        self.raw_text = raw_text
        self.provider_status = provider_status
        self.incomplete_details = incomplete_details
        self.http_status = http_status
        self.provider_body = provider_body

    def audit_record(self) -> dict[str, Any]:
        record: dict[str, Any] = {"failure_stage": self.failure_stage}
        optional = {
            "upstream_error_type": self.upstream_error_type,
            "raw_text": self.raw_text[:4000] if self.raw_text else None,
            "provider_status": self.provider_status,
            "incomplete_details": self.incomplete_details,
            "http_status": self.http_status,
            "provider_body": self.provider_body[:4000] if self.provider_body else None,
        }
        record.update({key: value for key, value in optional.items() if value is not None})
        return record


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _sha256_path(path: str | Path) -> str:
    return sha256(Path(path).read_bytes()).hexdigest()


def load_cases(path: str | Path) -> list[dict[str, Any]]:
    cases = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(cases, list) or not cases:
        raise ValueError("pilot cases must be a non-empty JSON list")
    case_ids: set[str] = set()
    for case in cases:
        case_id = str(case.get("id", "")).strip()
        if not case_id or case_id in case_ids:
            raise ValueError("pilot case IDs must be non-empty and unique")
        case_ids.add(case_id)
        facts = case.get("facts")
        if not isinstance(facts, list) or not facts:
            raise ValueError(f"pilot case {case_id} has no atomic facts")
        fact_ids = [fact.get("id") for fact in facts]
        if any(not fact_id for fact_id in fact_ids) or len(fact_ids) != len(set(fact_ids)):
            raise ValueError(f"pilot case {case_id} fact IDs must be non-empty and unique")
        gold = case.get("gold") or {}
        required_gold = {
            "violation_fact_ids",
            "evidence_adequacy",
            "disposition",
            "authorization_compliance",
        }
        if set(gold) != required_gold:
            raise ValueError(f"pilot case {case_id} has an invalid gold contract")
        if not set(gold["violation_fact_ids"]).issubset(set(fact_ids)):
            raise ValueError(f"pilot case {case_id} gold references an unknown fact")
    return cases


def _inventory_sha256(facts: list[dict[str, Any]]) -> str:
    ordered = sorted(facts, key=lambda fact: fact["id"])
    return sha256(_canonical_json(ordered).encode()).hexdigest()


def _graph_nodes(facts: list[dict[str, Any]]) -> list[dict[str, str]]:
    nodes: dict[str, dict[str, str]] = {}
    for fact in facts:
        for prefix in ("source", "target"):
            node_id = fact[f"{prefix}_id"]
            node = {
                "id": node_id,
                "type": fact[f"{prefix}_type"],
                "label": fact[f"{prefix}_label"],
            }
            if node_id in nodes and nodes[node_id] != node:
                raise ValueError(f"entity {node_id} has inconsistent labels across atomic facts")
            nodes[node_id] = node
    return [nodes[node_id] for node_id in sorted(nodes)]


def build_condition_views(case: dict[str, Any]) -> dict[str, dict[str, Any]]:
    facts = [dict(fact) for fact in case["facts"]]
    inventory_sha256 = _inventory_sha256(facts)
    common = {
        "case_id": case["id"],
        "title": case["title"],
        "fact_count": len(facts),
        "inventory_sha256": inventory_sha256,
    }
    b1 = {
        **common,
        "condition": "B1",
        "interface": "chronological_decision_ledger",
        "records": sorted(facts, key=lambda fact: (fact["sequence"], fact["id"])),
        "available_operations": ["lookup_by_fact_id", "filter_by_record_field"],
    }
    conflict_fact_ids = sorted(
        fact["id"]
        for fact in facts
        if fact.get("attributes", {}).get("review_signal")
        in {"violation", "conflict", "stale", "unobservable", "authorization_mismatch"}
    )
    evidence_fact_ids = sorted(
        fact["id"] for fact in facts if fact["source_type"] == "evidence"
    )
    current_support_fact_ids = sorted(
        fact["id"]
        for fact in facts
        if fact["source_type"] == "evidence"
        and fact.get("attributes", {}).get("outcome") == "supports"
        and fact.get("attributes", {}).get("freshness") == "current"
    )
    b2 = {
        **common,
        "condition": "B2",
        "interface": "relational_project_state_review",
        "nodes": _graph_nodes(facts),
        "relations": sorted(facts, key=lambda fact: fact["id"]),
        "computed_views": {
            "conflict_fact_ids": conflict_fact_ids,
            "evidence_coverage": {
                "evidence_fact_ids": evidence_fact_ids,
                "current_support_fact_ids": current_support_fact_ids,
            },
        },
        "available_operations": [
            "typed_traversal",
            "computed_conflict_view",
            "computed_evidence_coverage",
            "atomic_proposal_to_commit_gate",
        ],
    }
    return {"B1": b1, "B2": b2}


def fact_inventory_from_view(view: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if view.get("condition") == "B1":
        facts = view["records"]
    elif view.get("condition") == "B2":
        facts = view["relations"]
    else:
        raise ValueError("unknown pilot condition")
    return {fact["id"]: fact for fact in facts}


def score_response(case: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    gold = case["gold"]
    expected = set(gold["violation_fact_ids"])
    observed = set(response.get("violation_fact_ids") or [])
    true_positive = len(expected & observed)
    precision = true_positive / len(observed) if observed else (1.0 if not expected else 0.0)
    recall = true_positive / len(expected) if expected else (1.0 if not observed else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    violation_exact = int(expected == observed)
    evidence = int(response.get("evidence_adequacy") == gold["evidence_adequacy"])
    disposition = int(response.get("disposition") == gold["disposition"])
    authorization = int(
        response.get("authorization_compliance") == gold["authorization_compliance"]
    )
    return {
        "violation_identification": {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "exact": violation_exact,
        },
        "evidence_adequacy": evidence,
        "policy_compatible_disposition": disposition,
        "authorization_compliance": authorization,
        "all_dimensions_correct": int(
            violation_exact == 1 and evidence == 1 and disposition == 1 and authorization == 1
        ),
    }


def build_protocol_manifest(
    *,
    protocol_path: str | Path,
    cases_path: str | Path,
    prompt_path: str | Path,
    model: str,
    provider: str,
    repetitions: int,
    max_output_tokens: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    return {
        "format": "agentic-consensus/b1-b2-pilot-protocol@0.1",
        "protocol_sha256": _sha256_path(protocol_path),
        "cases_sha256": _sha256_path(cases_path),
        "prompt_sha256": _sha256_path(prompt_path),
        "conditions": ["B1", "B2"],
        "model": model,
        "provider": provider,
        "repetitions": repetitions,
        "sampling": "provider_default",
        "max_output_tokens": max_output_tokens,
        "timeout_seconds": timeout_seconds,
        "primary_dimensions": [
            "violation_identification",
            "evidence_adequacy",
            "policy_compatible_disposition",
            "authorization_compliance",
        ],
    }


class PilotModelClient:
    def __init__(
        self,
        config: LLMConfig,
        *,
        prompt: str,
        client: httpx.Client | None = None,
    ):
        if not config.enabled or not config.api_key or not config.model:
            raise ValueError("pilot model provider is not fully configured")
        if config.provider != OPENAI_RESPONSES_PROVIDER:
            raise ValueError("this frozen pilot supports the OpenAI Responses-compatible path")
        self.config = config
        self.prompt = prompt
        self.client = client

    def _endpoint(self) -> str:
        base = self.config.base_url.rstrip("/")
        if base.endswith("/responses"):
            return base
        if base.endswith("/v1"):
            return f"{base}/responses"
        return f"{base}/v1/responses"

    def review(self, view: dict[str, Any]) -> dict[str, Any]:
        body = {
            "model": self.config.model,
            "instructions": self.prompt,
            "input": "Assigned condition view (untrusted JSON data):\n" + _canonical_json(view),
            "max_output_tokens": self.config.max_tokens,
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "governed_change_decision",
                    "description": "Four-part decision for the information-matched B1/B2 pilot.",
                    "strict": True,
                    "schema": PILOT_RESPONSE_SCHEMA,
                }
            },
        }
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {self.config.api_key}",
        }
        if self.config.organization:
            headers["openai-organization"] = self.config.organization
        if self.config.project:
            headers["openai-project"] = self.config.project
        started = time.perf_counter()
        owns_client = self.client is None
        client = self.client or httpx.Client(timeout=self.config.timeout_seconds)
        try:
            try:
                response = client.post(self._endpoint(), headers=headers, json=body)
            except httpx.HTTPError as exc:
                raise PilotModelError(
                    str(exc),
                    failure_stage="transport",
                    upstream_error_type=type(exc).__name__,
                ) from exc
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise PilotModelError(
                    f"provider returned HTTP {response.status_code}",
                    failure_stage="provider_http",
                    upstream_error_type=type(exc).__name__,
                    http_status=response.status_code,
                    provider_body=response.text,
                ) from exc
            try:
                payload = response.json()
            except (json.JSONDecodeError, ValueError) as exc:
                raise PilotModelError(
                    "provider response was not JSON",
                    failure_stage="provider_payload",
                    upstream_error_type=type(exc).__name__,
                    provider_body=response.text,
                ) from exc
        finally:
            if owns_client:
                client.close()
        latency_ms = int((time.perf_counter() - started) * 1000)
        raw_text = ""
        for output in payload.get("output", []):
            for content in output.get("content", []):
                if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                    raw_text += content["text"]
        if not raw_text.strip():
            raise PilotModelError(
                "model response contains no output_text",
                failure_stage="response_validation",
                provider_status=payload.get("status"),
                incomplete_details=payload.get("incomplete_details"),
            )
        try:
            decision = PilotDecision.model_validate(json.loads(raw_text))
        except (json.JSONDecodeError, ValueError) as exc:
            raise PilotModelError(
                "model output failed the frozen decision schema",
                failure_stage="response_validation",
                upstream_error_type=type(exc).__name__,
                raw_text=raw_text,
                provider_status=payload.get("status"),
                incomplete_details=payload.get("incomplete_details"),
            ) from exc
        return {
            "response": decision.model_dump(),
            "usage": {
                key: int(value)
                for key, value in (payload.get("usage") or {}).items()
                if isinstance(value, (int, float))
            },
            "latency_ms": latency_ms,
            "provider": self.config.provider,
            "model": payload.get("model") or self.config.model,
            "raw_text": raw_text,
        }


def _mean(values: list[float | int]) -> float | None:
    return sum(values) / len(values) if values else None


def aggregate_trials(trials: list[dict[str, Any]]) -> dict[str, Any]:
    aggregates: dict[str, Any] = {}
    for condition in ("B1", "B2"):
        condition_trials = [item for item in trials if item["condition"] == condition]
        successful = [item for item in condition_trials if item.get("status") == "ok"]
        aggregates[condition] = {
            "trials": len(condition_trials),
            "successful_trials": len(successful),
            "failed_trials": len(condition_trials) - len(successful),
            "violation_f1": _mean(
                [item["scores"]["violation_identification"]["f1"] for item in successful]
            ),
            "violation_exact": _mean(
                [item["scores"]["violation_identification"]["exact"] for item in successful]
            ),
            "evidence_adequacy": _mean(
                [item["scores"]["evidence_adequacy"] for item in successful]
            ),
            "policy_compatible_disposition": _mean(
                [item["scores"]["policy_compatible_disposition"] for item in successful]
            ),
            "authorization_compliance": _mean(
                [item["scores"]["authorization_compliance"] for item in successful]
            ),
            "all_dimensions_correct": _mean(
                [item["scores"]["all_dimensions_correct"] for item in successful]
            ),
            "mean_latency_ms": _mean([item["latency_ms"] for item in successful]),
            "total_tokens": sum(
                item.get("usage", {}).get("total_tokens", 0) for item in successful
            ),
        }
    deltas = {}
    for metric in (
        "violation_f1",
        "violation_exact",
        "evidence_adequacy",
        "policy_compatible_disposition",
        "authorization_compliance",
        "all_dimensions_correct",
        "mean_latency_ms",
    ):
        b1 = aggregates["B1"][metric]
        b2 = aggregates["B2"][metric]
        deltas[f"{metric}_b2_minus_b1"] = b2 - b1 if b1 is not None and b2 is not None else None
    return {"conditions": aggregates, "deltas": deltas}


def _report_markdown(summary: dict[str, Any], manifest: dict[str, Any]) -> str:
    lines = [
        "# B1/B2 Exploratory Model Pilot",
        "",
        "This is an exploratory model-based manipulation pilot, not a human study or confirmatory evidence.",
        "",
        f"- Model: `{manifest['model']}`",
        f"- Repetitions: {manifest['repetitions']}",
        f"- Sampling: `{manifest['sampling']}`",
        f"- Maximum output tokens: {manifest['max_output_tokens']}",
        f"- Timeout seconds: {manifest['timeout_seconds']}",
        f"- Cases SHA-256: `{manifest['cases_sha256']}`",
        f"- Atomic inventories equal: `{str(summary['atomic_inventories_equal']).lower()}`",
        "",
        "| Condition | Successful | Violation F1 | Violation exact | Evidence | Disposition | Authorization | All four | Mean latency ms | Tokens |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for condition in ("B1", "B2"):
        item = summary["conditions"][condition]
        format_metric = lambda value: "NA" if value is None else f"{value:.3f}"
        lines.append(
            f"| {condition} | {item['successful_trials']}/{item['trials']} | "
            f"{format_metric(item['violation_f1'])} | {format_metric(item['violation_exact'])} | "
            f"{format_metric(item['evidence_adequacy'])} | "
            f"{format_metric(item['policy_compatible_disposition'])} | "
            f"{format_metric(item['authorization_compliance'])} | "
            f"{format_metric(item['all_dimensions_correct'])} | "
            f"{format_metric(item['mean_latency_ms'])} | {item['total_tokens']} |"
        )
    deltas = summary["deltas"]
    format_delta = lambda value: "NA" if value is None else f"{value:+.3f}"
    lines.extend(
        [
            "",
            "## Descriptive differences, B2 minus B1",
            "",
            f"- Violation F1: {format_delta(deltas['violation_f1_b2_minus_b1'])}",
            f"- Violation exact: {format_delta(deltas['violation_exact_b2_minus_b1'])}",
            f"- Evidence adequacy: {format_delta(deltas['evidence_adequacy_b2_minus_b1'])}",
            f"- Policy-compatible disposition: {format_delta(deltas['policy_compatible_disposition_b2_minus_b1'])}",
            f"- Authorization compliance: {format_delta(deltas['authorization_compliance_b2_minus_b1'])}",
            f"- All four: {format_delta(deltas['all_dimensions_correct_b2_minus_b1'])}",
            f"- Mean latency ms: {format_delta(deltas['mean_latency_ms_b2_minus_b1'])}",
            "",
            "## Evidence boundary",
            "",
            "The result validates the executable protocol and exposes descriptive model behavior under the two renderings. It does not estimate a human treatment effect, establish statistical significance, or prove that B2 offsets representation cost.",
            "",
        ]
    )
    return "\n".join(lines)


def run_pilot(
    *,
    cases: list[dict[str, Any]],
    reviewer: Any,
    manifest: dict[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    output = Path(output_dir)
    existing_names = {path.name for path in output.iterdir()} if output.exists() else set()
    if existing_names - {"manipulation-audit.json"}:
        raise FileExistsError(f"pilot output directory contains prior run artifacts: {output}")
    output.mkdir(parents=True, exist_ok=True)
    manifest = {
        **manifest,
        "started_at": datetime.now(UTC).isoformat(),
    }
    (output / "protocol-manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    trials: list[dict[str, Any]] = []
    trial_path = output / "trials.jsonl"
    trial_index = 0
    for repetition in range(manifest["repetitions"]):
        for case_index, case in enumerate(cases):
            views = build_condition_views(case)
            if fact_inventory_from_view(views["B1"]) != fact_inventory_from_view(views["B2"]):
                raise ValueError(f"atomic fact mismatch for case {case['id']}")
            order = ("B1", "B2") if (case_index + repetition) % 2 == 0 else ("B2", "B1")
            for condition in order:
                trial_index += 1
                base_record = {
                    "trial_index": trial_index,
                    "repetition": repetition + 1,
                    "case_id": case["id"],
                    "condition": condition,
                    "inventory_sha256": views[condition]["inventory_sha256"],
                    "fact_count": views[condition]["fact_count"],
                }
                try:
                    model_result = reviewer.review(views[condition])
                    trial = {
                        **base_record,
                        "status": "ok",
                        **model_result,
                        "scores": score_response(case, model_result["response"]),
                    }
                except Exception as exc:
                    trial = {
                        **base_record,
                        "status": "error",
                        "error_type": type(exc).__name__,
                        "error": str(exc)[:2000],
                    }
                    if isinstance(exc, PilotModelError):
                        trial["failure_details"] = exc.audit_record()
                trials.append(trial)
                with trial_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(trial, ensure_ascii=False, sort_keys=True) + "\n")
    summary = aggregate_trials(trials)
    summary.update(
        {
            "format": "agentic-consensus/b1-b2-pilot-results@0.1",
            "completed_at": datetime.now(UTC).isoformat(),
            "atomic_inventories_equal": True,
            "manifest": manifest,
        }
    )
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (output / "REPORT.md").write_text(
        _report_markdown(summary, manifest), encoding="utf-8"
    )
    return summary


def _default_output_dir(root: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return root / "runs" / stamp


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the information-matched B1/B2 pilot")
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.repetitions < 1 or args.repetitions > 20:
        parser.error("--repetitions must be between 1 and 20")
    root = Path(__file__).resolve().parent
    cases_path = root / "cases.json"
    protocol_path = root / "PROTOCOL.md"
    prompt_path = root / "REVIEW_PROMPT.txt"
    output = (args.output or _default_output_dir(root)).expanduser().resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"pilot output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    cases = load_cases(cases_path)
    audit_cases = []
    for case in cases:
        views = build_condition_views(case)
        equal = fact_inventory_from_view(views["B1"]) == fact_inventory_from_view(views["B2"])
        audit_cases.append(
            {
                "case_id": case["id"],
                "fact_count": len(case["facts"]),
                "b1_sha256": views["B1"]["inventory_sha256"],
                "b2_sha256": views["B2"]["inventory_sha256"],
                "inventories_equal": equal,
            }
        )
    audit = {
        "format": "agentic-consensus/b1-b2-manipulation-audit@0.1",
        "all_inventories_equal": all(item["inventories_equal"] for item in audit_cases),
        "cases": audit_cases,
    }
    (output / "manipulation-audit.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if not audit["all_inventories_equal"]:
        raise ValueError("B1/B2 atomic fact inventory mismatch")
    if args.dry_run:
        return 0

    config = LLMConfig.from_env()
    prompt = prompt_path.read_text(encoding="utf-8")
    manifest = build_protocol_manifest(
        protocol_path=protocol_path,
        cases_path=cases_path,
        prompt_path=prompt_path,
        model=config.model or "unconfigured",
        provider=config.provider,
        repetitions=args.repetitions,
        max_output_tokens=config.max_tokens,
        timeout_seconds=config.timeout_seconds,
    )
    reviewer = PilotModelClient(config, prompt=prompt)
    summary = run_pilot(
        cases=cases,
        reviewer=reviewer,
        manifest=manifest,
        output_dir=output,
    )
    failures = sum(
        summary["conditions"][condition]["failed_trials"] for condition in ("B1", "B2")
    )
    return 0 if failures == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
