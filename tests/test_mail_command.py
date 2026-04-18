"""Weaver mail commands route correctly through a WardenClient (mocked).

Tests the weaver → warden hop. The warden → weaver hop has its own test in
warden/tests/test_mail_worker_bridge.py.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any

import pytest
from click.testing import CliRunner

from weaver import guardian as services
from weaver.cli.dispatcher import cli


class _RecordingClient:
    """Stand-in for WardenClient that records every call made by weaver."""

    def __init__(self, payload_by_method: dict[str, Any] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.payloads = payload_by_method or {}

    def call(self, method: str, **params: Any) -> Any:
        self.calls.append((method, dict(params)))
        return self.payloads.get(method, [])


@pytest.fixture
def fake_client_factory(monkeypatch: pytest.MonkeyPatch):
    """Replace services.warden_client() with a context manager yielding our recorder."""
    recorder = _RecordingClient(payload_by_method={
        "mail.check": [
            {"uid": "1", "from": "x@y.z", "subject": "hi", "date": "2025-01-01T00:00:00"},
        ],
        "mail.wait_for": {"uid": "2", "from": "sender@site.example",
                          "subject": "code 123456", "date": "2025-01-02T00:00:00",
                          "text": "verify: https://site.example/v?t=abc", "urls": []},
        "mail.extract_verification_url": {"url": "https://site.example/v?t=abc",
                                          "code": "123456"},
    })

    @contextmanager
    def _ctx():
        yield recorder

    monkeypatch.setattr(services, "warden_client", _ctx)
    return recorder


def test_mail_latest_issues_mail_check_rpc(fake_client_factory: _RecordingClient) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["mail", "latest", "--context", "ai-corpus", "--limit", "3"])
    assert result.exit_code == 0
    method, params = fake_client_factory.calls[0]
    assert method == "mail.check"
    assert params == {"context": "ai-corpus", "limit": 3}


def test_mail_check_forwards_filters(fake_client_factory: _RecordingClient) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, [
        "mail", "check",
        "--context", "ai-corpus",
        "--from", "graphify.net",
        "--subject", "verify",
        "--limit", "10",
    ])
    assert result.exit_code == 0
    method, params = fake_client_factory.calls[0]
    assert method == "mail.check"
    assert params["from_domain"] == "graphify.net"
    assert params["subject_contains"] == "verify"
    assert params["limit"] == 10
    assert params["context"] == "ai-corpus"


def test_mail_wait_for_forwards_timeout(fake_client_factory: _RecordingClient) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, [
        "mail", "wait-for",
        "--context", "ai-corpus",
        "--from", "site.example",
        "--timeout", "90",
    ])
    assert result.exit_code == 0
    method, params = fake_client_factory.calls[0]
    assert method == "mail.wait_for"
    assert params == {"context": "ai-corpus", "from_domain": "site.example", "timeout_s": 90}


def test_mail_verify_url_returns_structured_payload(
    fake_client_factory: _RecordingClient,
) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, [
        "mail", "verify-url",
        "--context", "ai-corpus",
        "--from", "site.example",
        "--timeout", "30",
    ])
    assert result.exit_code == 0
    method, params = fake_client_factory.calls[0]
    assert method == "mail.extract_verification_url"
    assert params["from_domain"] == "site.example"
    assert params["timeout_s"] == 30
    body = json.loads(result.output)
    assert body["url"].startswith("https://site.example")
    assert body["code"] == "123456"


def test_mail_check_json_mode(fake_client_factory: _RecordingClient) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["mail", "latest", "--context", "ai-corpus", "--json"])
    assert result.exit_code == 0
    body = json.loads(result.output)
    assert isinstance(body, list)
    assert body[0]["uid"] == "1"


def test_mail_command_surface_warden_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """When warden is unreachable, weaver returns a clean ClickException."""
    @contextmanager
    def _bad():
        raise RuntimeError("warden daemon not running. Start it: weaver serve")
        yield None  # pragma: no cover

    monkeypatch.setattr(services, "warden_client", _bad)
    runner = CliRunner()
    result = runner.invoke(cli, ["mail", "latest", "--context", "ai-corpus"])
    assert result.exit_code != 0
    assert "not running" in result.output.lower()
