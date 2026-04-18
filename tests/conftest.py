"""Shared fixtures."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

import pytest


@pytest.fixture
def tmp_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Isolate weaver writes to a tmp repo-root."""
    # Redirect paths helpers to a throwaway repo root.
    repo_root = tmp_path / "weaver_repo"
    repo_root.mkdir()
    (repo_root / "pyproject.toml").write_text("[project]\nname='weaver'\nversion='0.1.0'\n")
    (repo_root / "_config").mkdir()
    (repo_root / "contexts").mkdir()

    from weaver import paths as p
    monkeypatch.setattr(p, "repo_root", lambda: repo_root)

    yield repo_root


@pytest.fixture(autouse=True)
def _no_user_keyring(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default: never touch the real OS keychain during tests."""
    monkeypatch.setenv("WEAVER_TEST_MODE", "1")


@pytest.fixture
def warden_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Redirect guardian/warden paths to a throwaway dir."""
    home = tmp_path / "warden"
    home.mkdir()
    monkeypatch.setenv("WARDEN_HOME", str(home))
    yield home
