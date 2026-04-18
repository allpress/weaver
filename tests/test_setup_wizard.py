from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from weaver.cli.commands import setup_cmd


@pytest.fixture
def spies(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state = {
        "init_called": 0,
        "spawned": 0,
        "wait_result": True,
        "cli_calls": [],
        "popen_stdin": None,
    }

    # warden already initialized: skip init path by default
    monkeypatch.setattr(setup_cmd.services, "warden_initialized", lambda: True)
    monkeypatch.setattr(setup_cmd.services, "warden_running", lambda: False)

    def fake_init() -> int:
        state["init_called"] += 1
        return 0

    def fake_spawn() -> None:
        state["spawned"] += 1

    def fake_wait(*, timeout_s: float = 0) -> bool:
        return state["wait_result"]

    monkeypatch.setattr(setup_cmd.services, "warden_init_via_cli", fake_init)
    monkeypatch.setattr(setup_cmd.services, "spawn_warden_detached", fake_spawn)
    monkeypatch.setattr(setup_cmd.services, "wait_for_warden", fake_wait)

    # Stub out external subprocess calls from setup_cmd itself
    def fake_check_call(args, **kwargs):
        state["cli_calls"].append(tuple(args))
        return 0

    class _FakePopen:
        def __init__(self, args, **kwargs):
            state["cli_calls"].append(tuple(args))
            self.returncode = 0

        def communicate(self, input: bytes | None = None) -> tuple[bytes, bytes]:
            state["popen_stdin"] = input
            return (b"", b"")

    monkeypatch.setattr(setup_cmd.subprocess, "check_call", fake_check_call)
    monkeypatch.setattr(setup_cmd.subprocess, "Popen", _FakePopen)
    return state


def test_setup_inits_when_needed(monkeypatch: pytest.MonkeyPatch, spies) -> None:
    monkeypatch.setattr(setup_cmd.services, "warden_initialized", lambda: False)
    report = setup_cmd.run_setup(
        context_name="ai-corpus",
        email_addr="doug.allpress.write@gmail.com",
        skip_gmail=True, start_warden=False,
        app_password_reader=lambda: "",
    )
    assert report.warden_inited is True
    assert spies["init_called"] == 1


def test_setup_spawns_warden_when_start_requested(spies) -> None:
    report = setup_cmd.run_setup(
        context_name="ai-corpus",
        email_addr="doug.allpress.write@gmail.com",
        skip_gmail=True, start_warden=True,
        app_password_reader=lambda: "",
    )
    assert spies["spawned"] == 1
    assert report.warden_started is True


def test_setup_refuses_start_when_warden_never_becomes_ready(
    monkeypatch: pytest.MonkeyPatch, spies,
) -> None:
    spies["wait_result"] = False
    with pytest.raises(Exception) as ei:
        setup_cmd.run_setup(
            context_name="ai-corpus",
            email_addr="x@y.z",
            skip_gmail=True, start_warden=True,
            app_password_reader=lambda: "",
        )
    assert "failed to start" in str(ei.value)


def test_setup_stores_app_password_via_weaver_cli(spies) -> None:
    report = setup_cmd.run_setup(
        context_name="ai-corpus",
        email_addr="doug.allpress.write@gmail.com",
        skip_gmail=False, start_warden=False,
        app_password_reader=lambda: "abcd efgh ijkl mnop",  # with spaces like Google UI
    )
    assert report.gmail_stored is True
    weaver_secret_cmds = [c for c in spies["cli_calls"] if c[:2] == ("weaver", "secret")]
    assert weaver_secret_cmds, f"no weaver secret call made; cli_calls={spies['cli_calls']}"
    assert "--from-stdin" in weaver_secret_cmds[0]
    # The stdin payload must be "email:password"
    assert spies["popen_stdin"] is not None
    assert spies["popen_stdin"].decode() == (
        "doug.allpress.write@gmail.com:abcd efgh ijkl mnop"
    )
    # (setup_cmd should NOT pre-strip spaces; the reader is responsible; the
    # default prompt reader strips, but our injected reader here does not.)


def test_default_prompt_reader_strips_nbsp(monkeypatch) -> None:
    """The default getpass-backed reader MUST strip NBSP; this is the path
    most users hit and the one that was broken."""
    nbsp_pw = "abcd\xa0efgh\xa0ijkl\xa0mnop"  # 19 chars
    monkeypatch.setattr(setup_cmd.getpass, "getpass", lambda prompt="": nbsp_pw)
    out = setup_cmd._prompt_app_password()
    assert len(out) == 16
    assert "\xa0" not in out
    assert " " not in out
    assert out == "abcdefghijklmnop"


def test_setup_skips_gmail_when_flag_set(spies) -> None:
    report = setup_cmd.run_setup(
        context_name="ai-corpus",
        email_addr="x@y.z",
        skip_gmail=True, start_warden=False,
        app_password_reader=lambda: "never-called",
    )
    assert report.gmail_stored is False
    # No weaver secret set should have been invoked
    weaver_secret_cmds = [c for c in spies["cli_calls"] if c[:2] == ("weaver", "secret")]
    assert weaver_secret_cmds == []


def test_setup_tolerates_duplicate_context(spies, monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess as sp

    def raise_duplicate(args, **kwargs):
        raise sp.CalledProcessError(1, args, output="already exists")

    monkeypatch.setattr(setup_cmd.subprocess, "check_call", raise_duplicate)

    report = setup_cmd.run_setup(
        context_name="ai-corpus",
        email_addr="x@y.z",
        skip_gmail=True, start_warden=False,
        app_password_reader=lambda: "",
    )
    assert report.weaver_context == "ai-corpus"
