from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from weaver.auth import (
    AuthenticationError,
    AuthResolver,
    SecretKind,
    SecretOrigin,
    SecretRef,
    SecretStore,
)
from weaver.config import ContextConfig, GlobalConfig


class _Memory(SecretStore):
    name = "memory"

    def __init__(self) -> None:
        self._blobs: dict[str, bytes] = {}
        self._refs: list[SecretRef] = []

    def is_available(self) -> bool: return True

    def _key(self, r: SecretRef) -> str:
        return f"{r.context}/{r.provider}/{r.kind.value}/{r.key}"

    def get(self, ref: SecretRef) -> bytes:
        return self._blobs[self._key(ref)]

    def put(self, ref: SecretRef, value: bytes) -> None:
        self._blobs[self._key(ref)] = value
        self._refs = [r for r in self._refs if self._key(r) != self._key(ref)]
        self._refs.append(ref)

    def delete(self, ref: SecretRef) -> None:
        self._blobs.pop(self._key(ref), None)
        self._refs = [r for r in self._refs if self._key(r) != self._key(ref)]

    def list(self, context, provider=None):
        return [r for r in self._refs if r.context == context
                and (provider is None or r.provider == provider)]


def _global_cfg() -> GlobalConfig:
    return GlobalConfig(
        default_context="t", parallel_workers=1, cache_freshness_hours=1,
        contexts_root=Path("/tmp"), proxy_cert_path=None,
        secrets_backend="auto", encrypted_file_path=Path("/tmp/x.enc"),
        parser_timeout_s=5, parser_max_bytes=1_000_000,
        rag_embedding_backend="sentence-transformers", rag_embedding_model="all-MiniLM-L6-v2",
        rag_chunk_size=800, rag_chunk_overlap=120, rag_top_k=5,
        graph_languages=["python"], graph_max_file_bytes=1_000_000,
        auth_strict_precedence=True, auth_allow_playwright_in_ci=False,
    )


def _context_cfg(**overrides) -> ContextConfig:
    base = dict(
        name="t", display_name="T", active=True,
        source_control_provider=None, source_control_base_url=None,
        source_control_group=None, source_control_clone_protocol="https",
        playwright_allowed={}, playwright_reasons={},
    )
    base.update(overrides)
    return ContextConfig(**base)


def test_api_token_wins_before_oauth() -> None:
    store = _Memory()
    ref = SecretRef(
        context="t", provider="gitlab", key="token",
        kind=SecretKind.api_token, origin=SecretOrigin.user_issued,
        created_at=datetime.utcnow(),
    )
    store.put(ref, b"abc123")

    resolver = AuthResolver(store, _global_cfg())
    result = resolver.resolve(_context_cfg(), "gitlab")
    assert result.bearer == "abc123"
    assert result.origin == SecretOrigin.user_issued


def test_raises_when_no_auth_available(monkeypatch) -> None:
    # Non-TTY so step 6 is skipped.
    import weaver.auth.resolver as r
    monkeypatch.setattr(r, "sys", type("S", (), {"stdin": type("I", (), {"isatty": lambda self: False})(),
                                                  "stdout": type("O", (), {"isatty": lambda self: False})()})())
    store = _Memory()
    resolver = AuthResolver(store, _global_cfg())
    with pytest.raises(AuthenticationError):
        resolver.resolve(_context_cfg(), "gitlab")


def test_playwright_scrape_blocked_unless_enabled() -> None:
    store = _Memory()
    resolver = AuthResolver(store, _global_cfg())
    # flag=True but no per-context opt-in: still blocked.
    with pytest.raises(AuthenticationError):
        resolver.resolve(_context_cfg(), "confluence",
                         dangerously_use_playwright_token=True)


def test_env_var_beats_stored_token(monkeypatch) -> None:
    monkeypatch.setenv("WEAVER_T_GITLAB_TOKEN", "env-value")
    store = _Memory()
    ref = SecretRef(
        context="t", provider="gitlab", key="token",
        kind=SecretKind.api_token, origin=SecretOrigin.user_issued,
        created_at=datetime.utcnow(),
    )
    store.put(ref, b"stored-value")
    resolver = AuthResolver(store, _global_cfg())
    result = resolver.resolve(_context_cfg(), "gitlab")
    assert result.bearer == "env-value"
    assert result.origin == SecretOrigin.env_var
