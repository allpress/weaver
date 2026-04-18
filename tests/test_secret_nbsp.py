"""Regression: Google's app-password UI pastes non-breaking spaces (\\xa0)
between 4-char groups. `weaver secret set --from-stdin` must strip ALL
whitespace from the password half of a basic_auth value before it lands in
the keychain, or IMAP login fails with UnicodeEncodeError or 'invalid
credentials'. This test is network-free; it monkeypatches the store.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from click.testing import CliRunner

from weaver.cli.dispatcher import cli
from weaver.auth.resolver import SecretRef


class _RecordingStore:
    name = "recording"

    def __init__(self) -> None:
        self.put_calls: list[tuple[SecretRef, bytes]] = []

    def is_available(self) -> bool:
        return True

    def put(self, ref: SecretRef, value: bytes) -> None:
        self.put_calls.append((ref, value))

    def list(self, *a: object, **kw: object) -> list[SecretRef]:
        return []

    def get(self, *a: object, **kw: object) -> bytes:
        raise NotImplementedError

    def delete(self, *a: object, **kw: object) -> None:
        raise NotImplementedError


@pytest.fixture
def recording_store(monkeypatch: pytest.MonkeyPatch) -> _RecordingStore:
    store = _RecordingStore()
    import weaver.cli.commands.secret_cmd as sc
    monkeypatch.setattr(sc, "get_default_store", lambda _cfg: store)
    monkeypatch.setattr(sc, "load_global", lambda: None)
    return store


def test_nbsp_stripped_from_basic_auth(recording_store: _RecordingStore) -> None:
    """19-char NBSP-padded input must land as 16-char password in the keychain."""
    raw = "doug.allpress.write@gmail.com:abcd\xa0efgh\xa0ijkl\xa0mnop"
    runner = CliRunner()
    result = runner.invoke(cli, [
        "secret", "set", "gmail", "app_password",
        "--context", "ai-corpus",
        "--kind", "basic_auth",
        "--origin", "user_issued",
        "--from-stdin",
    ], input=raw)
    assert result.exit_code == 0, result.output

    assert len(recording_store.put_calls) == 1
    ref, value = recording_store.put_calls[0]
    assert ref.provider == "gmail"
    assert ref.key == "app_password"
    stored = value.decode("utf-8")
    email, _, pw = stored.partition(":")
    assert email == "doug.allpress.write@gmail.com"
    assert pw == "abcdefghijklmnop"
    assert len(pw) == 16
    assert "\xa0" not in stored


def test_regular_spaces_also_stripped(recording_store: _RecordingStore) -> None:
    raw = "user@x.com:abcd efgh ijkl mnop"
    runner = CliRunner()
    result = runner.invoke(cli, [
        "secret", "set", "gmail", "app_password",
        "--context", "ai-corpus", "--kind", "basic_auth",
        "--origin", "user_issued", "--from-stdin",
    ], input=raw)
    assert result.exit_code == 0, result.output
    _, value = recording_store.put_calls[0]
    assert value.decode().partition(":")[2] == "abcdefghijklmnop"


def test_non_basic_auth_values_are_not_mutated(recording_store: _RecordingStore) -> None:
    """A token with embedded whitespace in kind=api_token should NOT be stripped."""
    raw = "ghp_AAAA BBBB CCCC DDDD"   # hypothetical token with spaces
    runner = CliRunner()
    result = runner.invoke(cli, [
        "secret", "set", "github", "token",
        "--context", "ai-corpus", "--kind", "api_token",
        "--origin", "user_issued", "--from-stdin",
    ], input=raw)
    assert result.exit_code == 0
    _, value = recording_store.put_calls[0]
    # api_token kind: never mutate.
    assert value.decode() == raw
