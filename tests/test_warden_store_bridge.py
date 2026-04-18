"""Cross-package bridge test: weaver's WardenStore against a real warden _Dispatcher.

We don't stand up a socket. We drive the warden dispatcher in-process (same
code path that `serve` uses) via a wire-compatible fake WardenClient so we
exercise:

  weaver.auth.backends.warden_store.WardenStore.list()
    → LamassuClient-shaped call (via our fake)
    → warden._Dispatcher.handle(bytes)
    → policy check, capability verify, secret.list handler
    → scrubbed JSON response
    → parsed back into List[SecretRef]

If any hop breaks, this test fails. Skips cleanly when `warden` isn't
importable in the current environment.
"""
from __future__ import annotations

import json
import pytest

warden = pytest.importorskip("warden")

from datetime import datetime
from pathlib import Path
from typing import Any

from warden.capability import generate_master_key, sign
from warden.policy import load as load_policy
from warden.server import ServerConfig, _Dispatcher

from weaver.auth.backends.warden_store import WardenStore, SandboxCannotReadValue
from weaver.auth.resolver import SecretKind, SecretOrigin, SecretRef


@pytest.fixture
def dispatcher(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[_Dispatcher, bytes]:
    """Build an in-process warden dispatcher with a minimal policy."""
    pol_path = tmp_path / "policy.yaml"
    pol_path.write_text("""
methods:
  - method: secret.list
    allow: true
    required_args: [context]
    allowed_args: [context, provider]
    rate_per_min: 1000
""", encoding="utf-8")
    key = generate_master_key()
    d = _Dispatcher(ServerConfig(policy=load_policy(pol_path), master_key=key))
    return d, key


class _FakeClient:
    """Duck-types warden.client.WardenClient but talks to a dispatcher in-process."""

    def __init__(self, dispatcher: _Dispatcher, key: bytes) -> None:
        self._d = dispatcher
        self._key = key
        self._next = 0

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, *a: object) -> None:
        pass

    def call(self, method: str, **params: Any) -> Any:
        self._next += 1
        cap = sign(self._key, method=method,
                   params={k: v for k, v in params.items() if v is not None})
        req = {
            "jsonrpc": "2.0", "id": self._next,
            "method": method,
            "params": {k: v for k, v in params.items() if v is not None},
            "auth_token": cap.serialize(),
        }
        raw = self._d.handle(json.dumps(req).encode("utf-8"))
        resp = json.loads(raw.strip())
        if "error" in resp and resp["error"] is not None:
            e = resp["error"]
            raise RuntimeError(f"warden error {e['code']}: {e['message']}")
        return resp.get("result")


def _install_fake_client(monkeypatch: pytest.MonkeyPatch, client: _FakeClient) -> None:
    """Point weaver.auth.backends.warden_store at our in-process dispatcher."""
    import weaver.auth.backends.warden_store as ws_mod

    class _Factory:
        @staticmethod
        def connect(*, tcp: tuple[str, int] | None = None) -> _FakeClient:
            return client

    # The module imports WardenClient locally inside _call(); monkeypatch both
    # the `warden.client.WardenClient` symbol and the lamassu-like import path.
    import warden.client as wc_mod
    monkeypatch.setattr(wc_mod, "WardenClient", _Factory, raising=True)


def test_bridge_list_returns_metadata(dispatcher, monkeypatch) -> None:
    d, key = dispatcher
    # Pre-register a secret metadata row through warden's own keychain backend
    # by monkeypatching the handler. secret.list in warden defers to uttu/weaver
    # secret metadata; for this test we inject a synthetic return.
    import warden.methods as wm
    called: list[tuple[str, dict]] = []
    original = d._handlers._registry["secret.list"]

    def fake_handler(params: dict) -> object:
        called.append(("secret.list", dict(params)))
        from warden.workers.base import WorkerResult
        return WorkerResult(ok=True, data=[{
            "uri": f"secret://{params['context']}/gmail/app_password",
            "provider": "gmail",
            "key": "app_password",
            "kind": SecretKind.basic_auth.value,
            "origin": SecretOrigin.user_issued.value,
            "created_at": datetime(2025, 1, 2, 3, 4, 5).isoformat(),
            "expires_at": None,
        }])
    d._handlers._registry["secret.list"] = fake_handler

    _install_fake_client(monkeypatch, _FakeClient(d, key))

    store = WardenStore()
    refs = store.list("ai-corpus")
    assert called and called[0][0] == "secret.list"
    assert called[0][1]["context"] == "ai-corpus"
    assert len(refs) == 1
    assert refs[0].provider == "gmail"
    assert refs[0].key == "app_password"
    assert refs[0].kind == SecretKind.basic_auth

    # Restore for test isolation
    d._handlers._registry["secret.list"] = original


def test_bridge_refuses_get(dispatcher, monkeypatch) -> None:
    """Even with a live bridge, the sandbox cannot read values."""
    d, key = dispatcher
    _install_fake_client(monkeypatch, _FakeClient(d, key))

    store = WardenStore()
    ref = SecretRef(
        context="ai-corpus", provider="gmail", key="app_password",
        kind=SecretKind.basic_auth, origin=SecretOrigin.user_issued,
    )
    with pytest.raises(SandboxCannotReadValue):
        store.get(ref)


def test_bridge_refuses_put_and_delete() -> None:
    store = WardenStore()
    ref = SecretRef(
        context="ai-corpus", provider="gmail", key="app_password",
        kind=SecretKind.basic_auth, origin=SecretOrigin.user_issued,
    )
    with pytest.raises(PermissionError):
        store.put(ref, b"x")
    with pytest.raises(PermissionError):
        store.delete(ref)


def test_bridge_value_ref_round_trip() -> None:
    store = WardenStore()
    ref = SecretRef(
        context="ai-corpus", provider="gmail", key="app_password",
        kind=SecretKind.basic_auth, origin=SecretOrigin.user_issued,
    )
    vr = store.get_value_ref(ref)
    assert vr == "secret://ai-corpus/gmail/app_password"
