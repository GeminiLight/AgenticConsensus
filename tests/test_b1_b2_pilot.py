import importlib
import importlib.util
import json
from pathlib import Path

import httpx
import pytest

from system.services.llm import LLMConfig

PILOT_DIR = Path(__file__).parents[1] / "evaluations" / "b1_b2_pilot"


def _pilot_module():
    try:
        spec = importlib.util.find_spec("evaluations.b1_b2_pilot.pilot")
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "the B1/B2 pilot harness is not implemented"
    return importlib.import_module("evaluations.b1_b2_pilot.pilot")


def test_b1_and_b2_are_generated_from_identical_canonical_atomic_facts():
    pilot = _pilot_module()
    cases = pilot.load_cases(PILOT_DIR / "cases.json")
    assert len(cases) >= 6

    for case in cases:
        views = pilot.build_condition_views(case)
        b1_inventory = pilot.fact_inventory_from_view(views["B1"])
        b2_inventory = pilot.fact_inventory_from_view(views["B2"])
        assert b1_inventory == b2_inventory == {
            fact["id"]: fact for fact in case["facts"]
        }
        assert views["B1"]["inventory_sha256"] == views["B2"]["inventory_sha256"]
        assert views["B1"]["fact_count"] == views["B2"]["fact_count"] == len(case["facts"])
        assert "computed_views" not in views["B1"]
        assert isinstance(views["B2"]["computed_views"]["conflict_fact_ids"], list)
        assert "gold" not in json.dumps(views, sort_keys=True).lower()


def test_pilot_scores_the_four_preregistered_decision_dimensions():
    pilot = _pilot_module()
    case = pilot.load_cases(PILOT_DIR / "cases.json")[1]
    gold = case["gold"]
    perfect = pilot.score_response(
        case,
        {
            "violation_fact_ids": gold["violation_fact_ids"],
            "evidence_adequacy": gold["evidence_adequacy"],
            "disposition": gold["disposition"],
            "authorization_compliance": gold["authorization_compliance"],
            "confidence": 0.9,
            "rationale": "The critical relation is unobservable and the only trace is stale.",
        },
    )
    assert perfect["violation_identification"]["f1"] == 1
    assert perfect["violation_identification"]["exact"] == 1
    assert perfect["evidence_adequacy"] == 1
    assert perfect["policy_compatible_disposition"] == 1
    assert perfect["authorization_compliance"] == 1
    assert perfect["all_dimensions_correct"] == 1

    partial = pilot.score_response(
        case,
        {
            "violation_fact_ids": gold["violation_fact_ids"][:1],
            "evidence_adequacy": "adequate",
            "disposition": "commit",
            "authorization_compliance": "compliant",
            "confidence": 0.8,
            "rationale": "Tests pass.",
        },
    )
    assert 0 < partial["violation_identification"]["recall"] < 1
    assert partial["evidence_adequacy"] == 0
    assert partial["policy_compatible_disposition"] == 0
    assert partial["all_dimensions_correct"] == 0


def test_protocol_manifest_freezes_inputs_without_secrets(tmp_path: Path):
    pilot = _pilot_module()
    manifest = pilot.build_protocol_manifest(
        protocol_path=PILOT_DIR / "PROTOCOL.md",
        cases_path=PILOT_DIR / "cases.json",
        prompt_path=PILOT_DIR / "REVIEW_PROMPT.txt",
        model="pilot-model",
        provider="openai_responses_compatible",
        repetitions=2,
        max_output_tokens=500,
        timeout_seconds=60,
    )

    assert manifest["protocol_sha256"]
    assert manifest["cases_sha256"]
    assert manifest["prompt_sha256"]
    assert manifest["conditions"] == ["B1", "B2"]
    assert manifest["repetitions"] == 2
    assert manifest["sampling"] == "provider_default"
    assert manifest["timeout_seconds"] == 60
    assert "temperature" not in manifest
    assert "api_key" not in json.dumps(manifest).lower()


def test_openai_responses_pilot_client_requests_strict_decision_json():
    pilot = _pilot_module()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/responses"
        assert request.headers["authorization"] == "Bearer synthetic-pilot-key"
        body = json.loads(request.content)
        assert body["store"] is False
        assert body["text"]["format"]["type"] == "json_schema"
        assert body["text"]["format"]["schema"]["additionalProperties"] is False
        assert body["max_output_tokens"] == 500
        assert "temperature" not in body
        assert "Assigned condition view" in body["input"]
        return httpx.Response(
            200,
            json={
                "model": "pilot-model",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    {
                                        "violation_fact_ids": [],
                                        "evidence_adequacy": "adequate",
                                        "disposition": "commit",
                                        "authorization_compliance": "compliant",
                                        "confidence": 0.9,
                                        "rationale": "Facts establish a safe authorized transition.",
                                    }
                                ),
                            }
                        ],
                    }
                ],
                "usage": {"input_tokens": 100, "output_tokens": 40, "total_tokens": 140},
            },
        )

    reviewer = pilot.PilotModelClient(
        LLMConfig(
            enabled=True,
            provider="openai_responses_compatible",
            api_key="synthetic-pilot-key",
            base_url="https://gateway.example.test/v1",
            model="pilot-model",
            max_tokens=500,
        ),
        prompt="Return the frozen reviewer JSON.",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = reviewer.review({"condition": "B1", "records": []})

    assert result["response"]["disposition"] == "commit"
    assert result["usage"]["total_tokens"] == 140
    assert result["provider"] == "openai_responses_compatible"
    assert "synthetic-pilot-key" not in json.dumps(result)


def test_model_parse_failure_preserves_bounded_raw_output_for_audit():
    pilot = _pilot_module()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "pilot-model",
                "status": "incomplete",
                "incomplete_details": {"reason": "max_output_tokens"},
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": '{"violation_fact_ids":["f1'}
                        ],
                    }
                ],
            },
        )

    reviewer = pilot.PilotModelClient(
        LLMConfig(
            enabled=True,
            provider="openai_responses_compatible",
            api_key="synthetic-pilot-key",
            base_url="https://gateway.example.test/v1",
            model="pilot-model",
            max_tokens=500,
        ),
        prompt="Return the frozen reviewer JSON.",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(pilot.PilotModelError) as caught:
        reviewer.review({"condition": "B1", "records": []})

    audit = caught.value.audit_record()
    assert audit["failure_stage"] == "response_validation"
    assert audit["raw_text"] == '{"violation_fact_ids":["f1'
    assert audit["provider_status"] == "incomplete"
    assert audit["incomplete_details"] == {"reason": "max_output_tokens"}
    assert "synthetic-pilot-key" not in json.dumps(audit)


def test_run_pilot_persists_every_trial_and_separate_condition_aggregates(tmp_path: Path):
    pilot = _pilot_module()
    cases = pilot.load_cases(PILOT_DIR / "cases.json")
    gold_by_case = {case["id"]: case["gold"] for case in cases}

    class PerfectReviewer:
        def review(self, view):
            gold = gold_by_case[view["case_id"]]
            return {
                "response": {
                    **gold,
                    "confidence": 0.9,
                    "rationale": "Grounded in the supplied atomic fact IDs.",
                },
                "usage": {"input_tokens": 100, "output_tokens": 40, "total_tokens": 140},
                "latency_ms": 10,
                "provider": "synthetic",
                "model": "perfect-reviewer",
                "raw_text": "synthetic",
            }

    manifest = pilot.build_protocol_manifest(
        protocol_path=PILOT_DIR / "PROTOCOL.md",
        cases_path=PILOT_DIR / "cases.json",
        prompt_path=PILOT_DIR / "REVIEW_PROMPT.txt",
        model="perfect-reviewer",
        provider="synthetic",
        repetitions=1,
        max_output_tokens=500,
        timeout_seconds=60,
    )
    run_output = tmp_path / "run"
    run_output.mkdir()
    (run_output / "manipulation-audit.json").write_text('{"all_inventories_equal":true}\n')
    summary = pilot.run_pilot(
        cases=cases,
        reviewer=PerfectReviewer(),
        manifest=manifest,
        output_dir=run_output,
    )

    trials = [json.loads(line) for line in (tmp_path / "run" / "trials.jsonl").read_text().splitlines()]
    assert len(trials) == len(cases) * 2
    assert {trial["condition"] for trial in trials} == {"B1", "B2"}
    assert summary["conditions"]["B1"]["all_dimensions_correct"] == 1
    assert summary["conditions"]["B2"]["all_dimensions_correct"] == 1
    assert (tmp_path / "run" / "protocol-manifest.json").is_file()
    assert (tmp_path / "run" / "summary.json").is_file()
    assert (tmp_path / "run" / "REPORT.md").is_file()
    report = (tmp_path / "run" / "REPORT.md").read_text()
    assert "Violation exact" in report
    assert "B2 minus B1" in report
    assert "Atomic inventories equal" in report


def test_pilot_cli_dry_run_writes_manipulation_audit_without_model_call(tmp_path: Path):
    pilot = _pilot_module()
    output = tmp_path / "dry-run"

    exit_code = pilot.main(["--dry-run", "--output", str(output), "--repetitions", "2"])

    assert exit_code == 0
    audit = json.loads((output / "manipulation-audit.json").read_text())
    assert audit["all_inventories_equal"] is True
    assert len(audit["cases"]) >= 6
    assert all(item["b1_sha256"] == item["b2_sha256"] for item in audit["cases"])
    assert not (output / "trials.jsonl").exists()
