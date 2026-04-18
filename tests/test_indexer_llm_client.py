"""LLM client tests: mock httpx, verify retry-on-invalid-JSON, verify error mapping."""
from __future__ import annotations

import json
from typing import Any

import pytest

from weaver.indexer.llm_client import (
    LLMCompletion,
    OllamaClient,
    OllamaConnectionError,
    OllamaError,
    OllamaValidationError,
    parse_json_with_retry,
)
from weaver.indexer.models import ExtractedArticle


class _MockResp:
    def __init__(self, status_code: int, payload: Any = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self) -> Any:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _MockClient:
    def __init__(self, responses: list[_MockResp]) -> None:
        self._responses = list(responses)
        self.posts: list[dict[str, Any]] = []
        self.gets: list[tuple[str, dict[str, Any]]] = []

    def post(self, path: str, *, json: dict[str, Any], timeout: float) -> _MockResp:
        self.posts.append({"path": path, "json": json, "timeout": timeout})
        return self._responses.pop(0)

    def get(self, path: str, *, timeout: float) -> _MockResp:
        self.gets.append((path, {"timeout": timeout}))
        return self._responses.pop(0)

    def close(self) -> None:
        pass


def test_health_returns_installed_models(monkeypatch: pytest.MonkeyPatch) -> None:
    mock = _MockClient([_MockResp(200, {
        "models": [{"name": "qwen2.5:7b"}, {"name": "llama3.2:3b"}],
    })])
    client = OllamaClient(model="qwen2.5:7b")
    monkeypatch.setattr(client, "_get_client", lambda: mock)

    info = client.health()
    assert info["host"].startswith("http")
    assert "qwen2.5:7b" in info["models"]
    assert "llama3.2:3b" in info["models"]


def test_complete_json_posts_correct_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    mock = _MockClient([_MockResp(200, {
        "model": "qwen2.5:7b",
        "message": {"role": "assistant", "content": '{"summary": "ok"}'},
        "total_duration": 123_000_000,
        "prompt_eval_count": 10,
        "eval_count": 20,
    })])
    client = OllamaClient(model="qwen2.5:7b", num_ctx=8192)
    monkeypatch.setattr(client, "_get_client", lambda: mock)

    out = client.complete_json(system="sys", user="usr")
    assert isinstance(out, LLMCompletion)
    assert out.content == '{"summary": "ok"}'
    assert out.prompt_tokens == 10
    assert out.completion_tokens == 20
    assert out.total_duration_ms == 123   # nanoseconds → ms

    body = mock.posts[0]["json"]
    assert body["format"] == "json"
    assert body["stream"] is False
    assert body["model"] == "qwen2.5:7b"
    assert body["options"]["num_ctx"] == 8192
    assert body["options"]["temperature"] == 0.0
    assert body["messages"][0] == {"role": "system", "content": "sys"}
    assert body["messages"][1] == {"role": "user", "content": "usr"}


def test_404_raises_pull_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    mock = _MockClient([_MockResp(404, None, text="model not found")])
    client = OllamaClient(model="qwen2.5:7b")
    monkeypatch.setattr(client, "_get_client", lambda: mock)

    with pytest.raises(OllamaConnectionError, match="ollama pull"):
        client.complete_json(system="", user="")


def test_parse_json_with_retry_success_first_try() -> None:
    class _Stub:
        model = "m"
        def complete_json(self, *, system: str, user: str,
                          temperature: float = 0.0, timeout_s: float = 0) -> LLMCompletion:
            return LLMCompletion(model="m", content='{"summary": "hi"}')
    out, completion = parse_json_with_retry(
        _Stub(), system="", user="",
        validator=ExtractedArticle.model_validate,
    )
    assert out.summary == "hi"
    assert completion.model == "m"


def test_parse_json_with_retry_recovers_from_bad_json() -> None:
    calls: list[str] = []

    class _Stub:
        model = "m"
        def complete_json(self, *, system: str, user: str,
                          temperature: float = 0.0, timeout_s: float = 0) -> LLMCompletion:
            calls.append(user)
            if len(calls) == 1:
                return LLMCompletion(model="m", content="not json at all")
            return LLMCompletion(model="m", content='{"summary":"good"}')

    out, _ = parse_json_with_retry(
        _Stub(), system="", user="extract",
        validator=ExtractedArticle.model_validate, max_retries=1,
    )
    assert out.summary == "good"
    # Second call's user prompt includes the parse-error nudge
    assert "not valid JSON" in calls[1]


def test_parse_json_with_retry_recovers_from_schema_mismatch() -> None:
    calls: list[str] = []

    class _Stub:
        model = "m"
        def complete_json(self, *, system: str, user: str,
                          temperature: float = 0.0, timeout_s: float = 0) -> LLMCompletion:
            calls.append(user)
            if len(calls) == 1:
                return LLMCompletion(model="m", content='{"wrong_key": 1}')
            return LLMCompletion(model="m", content='{"summary":"fixed"}')

    out, _ = parse_json_with_retry(
        _Stub(), system="", user="extract",
        validator=ExtractedArticle.model_validate, max_retries=1,
    )
    assert out.summary == "fixed"
    assert "didn't match the schema" in calls[1]


def test_parse_json_with_retry_exhausted_raises() -> None:
    class _BadStub:
        model = "m"
        def complete_json(self, *, system: str, user: str,
                          temperature: float = 0.0, timeout_s: float = 0) -> LLMCompletion:
            return LLMCompletion(model="m", content="never json")

    with pytest.raises(OllamaValidationError, match="after 2 attempts"):
        parse_json_with_retry(
            _BadStub(), system="", user="",
            validator=ExtractedArticle.model_validate, max_retries=1,
        )
