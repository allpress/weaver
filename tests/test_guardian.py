from __future__ import annotations

import os
from pathlib import Path

import pytest

from weaver import guardian as services


def test_warden_home_respects_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("WARDEN_HOME", str(tmp_path))
    assert services.warden_home() == tmp_path


def test_warden_socket_respects_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("WARDEN_SOCKET", str(tmp_path / "sock"))
    assert services.warden_socket() == tmp_path / "sock"


def test_pid_alive_false_when_missing(tmp_path: Path) -> None:
    assert services._pid_alive(tmp_path / "nope.pid") is False


def test_pid_alive_true_for_current_process(tmp_path: Path) -> None:
    pid_file = tmp_path / "pid"
    pid_file.write_text(str(os.getpid()))
    assert services._pid_alive(pid_file) is True


def test_warden_running_false_when_no_socket(warden_home: Path) -> None:
    assert services.warden_running() is False


def test_warden_initialized_false_when_fresh(warden_home: Path) -> None:
    assert services.warden_initialized() is False


def test_warden_initialized_true_when_files_present(warden_home: Path) -> None:
    (warden_home / "cap.token").write_text("deadbeef")
    (warden_home / "policy.yaml").write_text("methods: []\n")
    assert services.warden_initialized() is True


def test_health_reports_each_field(warden_home: Path) -> None:
    h = services.health()
    assert isinstance(h.warden_socket_exists, bool)
    assert isinstance(h.warden_pid_alive, bool)
    assert isinstance(h.warden_token_present, bool)
    assert isinstance(h.warden_policy_present, bool)


def test_warden_client_raises_when_not_initialized(warden_home: Path) -> None:
    with pytest.raises(RuntimeError, match="not initialized"):
        with services.warden_client():
            pass


def test_warden_client_raises_when_daemon_dead(warden_home: Path) -> None:
    (warden_home / "cap.token").write_text("x")
    (warden_home / "policy.yaml").write_text("methods: []\n")
    # No pid / no socket → "not running"
    with pytest.raises(RuntimeError, match="not running"):
        with services.warden_client():
            pass
