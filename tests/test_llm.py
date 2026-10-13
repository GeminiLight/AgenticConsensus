import httpx
import pytest


@pytest.mark.parametrize("base, endpoint", [
    ("https://gateway.example.test", "/v1/chat/completions"),
    ("https://gateway.example.test/v1/", "/v1/chat/completions"),
    ("https://gateway.example.test/api/coding/paas/v4", "/api/coding/paas/v4/chat/completions"),
    ("https://gateway.example.test/custom/api", "/custom/api/chat/completions"),
    ("https://gateway.example.test/api/v4/chat/completions", "/api/v4/chat/completions"),
])
def test_chat_endpoint_respects_explicit_provider_base_path(base, endpoint):
    gateway = EvidenceSummarizer(LLMConfig(provider="openai_chat_completions_compatible", base_url=base))
    assert httpx.URL(gateway._endpoint()).path == endpoint


def test_anthropic_proxy_keeps_existing_version_suffix_behavior():
    gateway = EvidenceSummarizer(LLMConfig(base_url="https://gateway.test/anthropic"))
    assert gateway._endpoint() == "https://gateway.test/anthropic/v1/messages"


def test_structured_repair_still_marked_truncated_is_not_accepted():
    def handler(request):
        return httpx.Response(200, json={"choices": [{"finish_reason": "length", "message": {"content": '{"answer":"cut short"}'}}]})
    gateway = EvidenceSummarizer(LLMConfig(enabled=True, provider="openai_chat_completions_compatible", api_key="synthetic", model="test"),
        client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = gateway.generate_json(system_prompt="Only JSON", data={}, schema={"type":"object", "required":["answer"], "properties":{"answer":{"type":"string"}}}, schema_name="answer", schema_description="answer")
    assert result.source == "deterministic" and result.payload is None

from system.services.llm import EvidenceSummarizer, LLMConfig, SummaryResult


def test_disabled_model_uses_deterministic_summary():
    summarizer = EvidenceSummarizer(LLMConfig(enabled=False))
    result = summarizer.summarize(
        {
            "tests": "pass",
            "findings": [{"kind": "forbidden_dependency", "severity": "critical"}],
            "patch_summary": "1 file changed",
        }
    )
    assert result.source == "deterministic"
    assert "critical" in result.summary.lower()
    assert "tests passed" in result.summary.lower()
    assert "finding(s)" not in result.summary


def test_anthropic_compatible_request_is_bounded_and_validated():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/messages"
        assert request.headers["x-api-key"] == "synthetic-test-token"
        body = __import__("json").loads(request.content)
        assert body["max_tokens"] == 200
        assert "advisory" in body["system"].lower()
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": '{"summary":"Tests pass but the boundary is violated.","risks":["legacy dependency"]}'}],
                "usage": {"input_tokens": 40, "output_tokens": 18},
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    summarizer = EvidenceSummarizer(
        LLMConfig(
            enabled=True,
            api_key="synthetic-test-token",
            base_url="https://gateway.example.test",
            model="test-model",
            max_tokens=200,
        ),
        client=client,
    )
    result = summarizer.summarize({"tests": "pass", "findings": [], "patch_summary": "small"})
    assert isinstance(result, SummaryResult)
    assert result.source == "model"
    assert result.provider == "anthropic_messages_compatible"
    assert result.usage["output_tokens"] == 18


def test_plain_text_gateway_response_remains_bounded_advisory_output():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "Tests pass, but the new legacy dependency remains an open critical risk."}],
                "usage": {"input_tokens": 20, "output_tokens": 14},
            },
        )

    summarizer = EvidenceSummarizer(
        LLMConfig(enabled=True, api_key="synthetic", model="test-model", max_tokens=100),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = summarizer.summarize({"tests": "pass", "findings": []})
    assert result.source == "model"
    assert result.fallback_reason == "provider returned plain text instead of JSON"
    assert len(result.summary) <= 1800


def test_openai_responses_compatible_request_and_response():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/responses"
        assert request.headers["authorization"] == "Bearer openai-test-key"
        body = __import__("json").loads(request.content)
        assert body["max_output_tokens"] == 180
        assert body["store"] is False
        assert body["text"]["format"]["type"] == "json_schema"
        assert body["text"]["format"]["strict"] is True
        assert body["text"]["format"]["schema"]["required"] == ["summary", "risks"]
        assert body["text"]["format"]["schema"]["additionalProperties"] is False
        assert "advisory" in body["instructions"].lower()
        return httpx.Response(
            200,
            json={
                "model": "gpt-test",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": '{"summary":"Tests pass but one critical boundary risk remains.","risks":["legacy import"]}',
                            }
                        ],
                    }
                ],
                "usage": {"input_tokens": 35, "output_tokens": 17, "total_tokens": 52},
            },
        )

    summarizer = EvidenceSummarizer(
        LLMConfig(
            enabled=True,
            provider="openai_responses_compatible",
            api_key="openai-test-key",
            base_url="https://gateway.example.test/v1",
            model="gpt-test",
            max_tokens=180,
        ),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = summarizer.summarize({"tests": "pass", "findings": []})
    assert result.source == "model"
    assert result.provider == "openai_responses_compatible"
    assert result.usage["total_tokens"] == 52


def test_openai_chat_completions_compatible_request_and_response():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        body = __import__("json").loads(request.content)
        assert body["max_completion_tokens"] == 160
        assert body["messages"][0]["role"] == "system"
        assert body["response_format"]["type"] == "json_schema"
        assert body["response_format"]["json_schema"]["strict"] is True
        return httpx.Response(
            200,
            json={
                "model": "chat-test",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": '{"summary":"The evidence remains incomplete for approval.","risks":[]}',
                        }
                    }
                ],
                "usage": {"prompt_tokens": 25, "completion_tokens": 12, "total_tokens": 37},
            },
        )

    summarizer = EvidenceSummarizer(
        LLMConfig(
            enabled=True,
            provider="openai_chat_completions_compatible",
            api_key="openai-test-key",
            base_url="https://gateway.example.test",
            model="chat-test",
            max_tokens=160,
        ),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = summarizer.summarize({"tests": "unknown", "findings": []})
    assert result.source == "model"
    assert result.provider == "openai_chat_completions_compatible"
    assert result.usage["output_tokens"] == 12


def test_openai_chat_gateway_can_disable_reasoning(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CONSENSUS_LLM_ENABLED", "true")
    monkeypatch.setenv("CONSENSUS_LLM_PROVIDER", "openai_chat")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    monkeypatch.setenv("OPENAI_MODEL", "reasoning-test-model")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://gateway.example.test/v1")
    monkeypatch.setenv("OPENAI_CHAT_THINKING", "disabled")

    def handler(request: httpx.Request) -> httpx.Response:
        body = __import__("json").loads(request.content)
        assert body["thinking"] == {"type": "disabled"}
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"summary":"The bounded summary remains available.","risks":[]}'
                        }
                    }
                ]
            },
        )

    config = LLMConfig.from_env()
    summarizer = EvidenceSummarizer(
        config,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = summarizer.summarize({"tests": "pass", "findings": []})

    assert result.source == "model"
    assert config.chat_thinking == "disabled"


def test_openai_compatible_gateway_can_use_legacy_json_object_mode():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(__import__("json").loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": '{"summary":"A bounded compatible response is available.","risks":[]}'}}
                ]
            },
        )

    summarizer = EvidenceSummarizer(
        LLMConfig(
            enabled=True,
            provider="openai_chat_completions_compatible",
            api_key="synthetic",
            base_url="https://gateway.example.test",
            model="chat-test",
            structured_output="json_object",
        ),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = summarizer.summarize({"tests": "pass", "findings": []})
    assert result.source == "model"
    assert captured["response_format"] == {"type": "json_object"}


def test_environment_auto_selects_openai_without_exposing_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CONSENSUS_LLM_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-exposed")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")
    monkeypatch.setenv("CONSENSUS_LLM_PROVIDER", "auto")
    config = LLMConfig.from_env()
    assert config.provider == "openai_responses_compatible"
    assert config.runtime_status() == {
        "enabled": True,
        "configured": True,
        "provider": "openai_responses_compatible",
        "model": "gpt-test",
        "api_style": "responses",
        "structured_output": "json_schema",
    }
    assert "must-not-be-exposed" not in str(config.runtime_status())


def test_structured_generation_repairs_one_non_json_compatible_gateway_response():
    responses = iter(
        [
            "The answer is grounded, but I did not return JSON.",
            '{"answer":"Grounded answer","citation_ids":["evidence:one"]}',
        ]
    )
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = __import__("json").loads(request.content)
        requests.append(body)
        return httpx.Response(
            200,
            json={
                "model": "compatible-test",
                "choices": [{"message": {"content": next(responses)}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
            },
        )

    gateway = EvidenceSummarizer(
        LLMConfig(
            enabled=True,
            provider="openai_chat_completions_compatible",
            api_key="synthetic",
            base_url="https://gateway.example.test/v1",
            model="compatible-test",
        ),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = gateway.generate_json(
        system_prompt="Return a grounded answer.",
        data={"cards": [{"id": "evidence:one"}]},
        schema={
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
                "citation_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["answer", "citation_ids"],
            "additionalProperties": False,
        },
        schema_name="grounded_answer",
        schema_description="A grounded answer.",
    )

    assert len(requests) == 2
    assert "previous_output" in requests[1]["messages"][-1]["content"]
    assert result.source == "model"
    assert result.payload["answer"] == "Grounded answer"
    assert result.usage["total_tokens"] == 16


def test_structured_generation_fails_closed_when_repair_is_still_invalid():
    responses = iter(["not json", '{"answer":"still missing citations"}'])

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "compatible-test",
                "choices": [{"message": {"content": next(responses)}}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
            },
        )

    gateway = EvidenceSummarizer(
        LLMConfig(
            enabled=True,
            provider="openai_chat_completions_compatible",
            api_key="synthetic",
            base_url="https://gateway.example.test/v1",
            model="compatible-test",
        ),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = gateway.generate_json(
        system_prompt="Return a grounded answer.",
        data={"cards": []},
        schema={
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
                "citation_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["answer", "citation_ids"],
            "additionalProperties": False,
        },
        schema_name="grounded_answer",
        schema_description="A grounded answer.",
    )

    assert result.source == "deterministic"
    assert result.payload is None
    assert "structured model output unavailable" in result.fallback_reason


def test_structured_generation_fails_closed_on_gateway_http_error():
    gateway = EvidenceSummarizer(
        LLMConfig(
            enabled=True,
            provider="openai_responses_compatible",
            api_key="synthetic",
            base_url="https://api.openai.com/v1",
            model="gpt-test",
        ),
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(502, json={"error": "upstream unavailable"})
            )
        ),
    )
    result = gateway.generate_json(
        system_prompt="Return one object.",
        data={},
        schema={
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
            "additionalProperties": False,
        },
        schema_name="answer",
        schema_description="One answer.",
    )

    assert result.source == "deterministic"
    assert result.payload is None
    assert result.fallback_reason.startswith("HTTPStatusError:")


def test_env_file_is_loaded_without_overriding_process_environment(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "CONSENSUS_LLM_ENABLED=true",
                "CONSENSUS_LLM_PROVIDER=openai_responses",
                "OPENAI_API_KEY=file-only-secret",
                "OPENAI_MODEL=file-model",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("CONSENSUS_LLM_ENABLED", raising=False)
    monkeypatch.delenv("CONSENSUS_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_MODEL", "process-model")

    config = LLMConfig.from_env(env_file)

    assert config.enabled is True
    assert config.provider == "openai_responses_compatible"
    assert config.model == "process-model"
    assert config.runtime_status()["configured"] is True
    assert "file-only-secret" not in str(config.runtime_status())


def test_truncated_structured_output_is_repaired_with_a_larger_compact_budget():
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read().decode()
        import json as _json

        payload = _json.loads(body)
        requests.append(payload)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "finish_reason": "length",
                            "message": {"role": "assistant", "content": '{"answer": "A long answer that never'},
                        }
                    ],
                    "usage": {"prompt_tokens": 40, "completion_tokens": 700, "total_tokens": 740},
                },
            )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": '{"answer": "A short answer", "citation_ids": ["evidence:one"]}',
                        },
                    }
                ],
                "usage": {"prompt_tokens": 60, "completion_tokens": 20, "total_tokens": 80},
            },
        )

    gateway = EvidenceSummarizer(
        LLMConfig(
            enabled=True,
            provider="openai_chat_completions_compatible",
            api_key="synthetic",
            base_url="https://gateway.example.test/v1",
            model="compatible-test",
            max_tokens=700,
        ),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = gateway.generate_json(
        system_prompt="Return a grounded answer.",
        data={"cards": [{"id": "evidence:one"}]},
        schema={
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
                "citation_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["answer", "citation_ids"],
            "additionalProperties": False,
        },
        schema_name="grounded_answer",
        schema_description="A grounded answer.",
    )

    assert len(requests) == 2
    assert "fit within 700 tokens" in requests[0]["messages"][0]["content"]
    assert requests[0]["max_completion_tokens"] == 700
    assert requests[1]["max_completion_tokens"] == 1400
    assert "cut off" in requests[1]["messages"][0]["content"]
    assert result.source == "model"
    assert result.payload["answer"] == "A short answer"
    assert result.fallback_reason == "provider output repaired to requested schema"
    assert result.usage["total_tokens"] == 820
