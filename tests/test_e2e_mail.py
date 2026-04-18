"""End-to-end: weaver mail latest → warden dispatcher → mail worker (mocked IMAP).

Covers the full command chain:
  click.CliRunner → weaver.cli → weaver.services.warden_client (patched to yield
  an in-process client) → warden._Dispatcher.handle → policy + cap check →
  methods.registry[mail.check] → MailWorker._build_provider (patched) →
  weaver.providers.mail.base.MailMessage shape → MailWorker._summary() →
  WorkerResult → scrub → click.echo

Network-free; both warden and weaver must be importable.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

warden = pytest.importorskip("warden")
weaver = pytest.importorskip("weaver")

from warden.capability import generate_master_key, sign
from warden.policy import load as load_policy
from warden.server import ServerConfig, _Dispatcher

from weaver.providers.mail.base import MailMessage

from weaver import guardian as services
from weaver.cli.dispatcher import cli


@pytest.fixture
def live_dispatcher(tmp_path: Path) -> tuple[_Dispatcher, bytes]:
    pol = tmp_path / "policy.yaml"
    pol.write_text("""
methods:
  - method: mail.check
    allow: true
    required_args: [context]
    allowed_args: [context, from_domain, subject_contains, since, limit, mailbox]
    arg_limits:
      max_limit: 50
    scope:
      allowed_mailboxes: [INBOX]
    rate_per_min: 1000
""", encoding="utf-8")
    key = generate_master_key()
    d = _Dispatcher(ServerConfig(policy=load_policy(pol), master_key=key))
    return d, key


class _InProcClient:
    """Wire-compatible with WardenClient, routes through the dispatcher."""

    def __init__(self, d: _Dispatcher, key: bytes) -> None:
        self._d = d
        self._key = key
        self._n = 0

    def call(self, method: str, **params: Any) -> Any:
        self._n += 1
        clean = {k: v for k, v in params.items() if v is not None}
        cap = sign(self._key, method=method, params=clean)
        req = {
            "jsonrpc": "2.0", "id": self._n,
            "method": method, "params": clean,
            "auth_token": cap.serialize(),
        }
        raw = self._d.handle(json.dumps(req).encode("utf-8"))
        resp = json.loads(raw.strip())
        if "error" in resp and resp["error"] is not None:
            e = resp["error"]
            raise RuntimeError(f"warden error {e['code']}: {e['message']}")
        return resp.get("result")


class _StubProvider:
    @contextmanager
    def session(self):
        yield self

    def check(self, **kw: Any):
        return iter([MailMessage(
            uid="1001", from_addr="news@martinfowler.com", from_name="Martin",
            to_addrs=("doug.allpress.write@gmail.com",),
            subject="Refactoring weekly",
            date=datetime(2025, 4, 1, 12, 0, tzinfo=timezone.utc),
            text_body="hello", html_body="", headers={},
        )])


def test_e2e_weaver_mail_latest_hits_dispatcher(
    live_dispatcher: tuple[_Dispatcher, bytes],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    d, key = live_dispatcher

    # Patch weaver.services.warden_client to yield our in-process client.
    @contextmanager
    def _fake_ctx():
        yield _InProcClient(d, key)

    monkeypatch.setattr(services, "warden_client", _fake_ctx)

    # Patch MailWorker._build_provider so no IMAP is attempted.
    from warden.workers.mail_worker import MailWorker
    monkeypatch.setattr(MailWorker, "_build_provider", lambda self: _StubProvider())

    runner = CliRunner()
    result = runner.invoke(cli, ["mail", "latest", "--context", "ai-corpus",
                                  "--limit", "3", "--json"])
    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert isinstance(body, list) and len(body) == 1
    assert body[0]["uid"] == "1001"
    assert body[0]["from"] == "news@martinfowler.com"


def test_e2e_policy_blocks_excessive_limit(
    live_dispatcher: tuple[_Dispatcher, bytes],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guardian should reject before the worker is invoked."""
    d, key = live_dispatcher

    @contextmanager
    def _fake_ctx():
        yield _InProcClient(d, key)

    monkeypatch.setattr(services, "warden_client", _fake_ctx)

    # If mail worker were invoked, this would raise loudly — we want the
    # policy to refuse before we get there.
    from warden.workers.mail_worker import MailWorker
    def _boom(self: Any) -> Any:
        raise AssertionError("worker should not have been invoked")
    monkeypatch.setattr(MailWorker, "_build_provider", _boom)

    runner = CliRunner()
    result = runner.invoke(cli, ["mail", "check", "--context", "ai-corpus",
                                  "--limit", "9999"])
    assert result.exit_code != 0
    assert "exceeds cap" in result.output or "policy" in result.output.lower()


def test_e2e_mailbox_scope_enforced(
    live_dispatcher: tuple[_Dispatcher, bytes],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """mailbox outside allowed_mailboxes → policy denial."""
    d, key = live_dispatcher

    @contextmanager
    def _fake_ctx():
        yield _InProcClient(d, key)

    monkeypatch.setattr(services, "warden_client", _fake_ctx)

    runner = CliRunner()
    result = runner.invoke(cli, ["mail", "check", "--context", "ai-corpus",
                                  "--mailbox", "[Gmail]/Drafts"])
    assert result.exit_code != 0
    assert "scope" in result.output.lower() or "not in scope" in result.output.lower()
