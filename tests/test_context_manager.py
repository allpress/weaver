from __future__ import annotations

from pathlib import Path

import pytest

from weaver import context_manager


def test_create_and_summary(tmp_context: Path) -> None:
    ctx = "team-alpha"
    context_manager.create(ctx, display_name="Team Alpha")
    s = context_manager.summary(ctx)
    assert s.name == ctx
    assert s.display_name == "Team Alpha"
    assert s.repos == 0


def test_duplicate_create_fails(tmp_context: Path) -> None:
    context_manager.create("x")
    with pytest.raises(FileExistsError):
        context_manager.create("x")


def test_invalid_name(tmp_context: Path) -> None:
    with pytest.raises(ValueError):
        context_manager.create("has spaces")


def test_delete_requires_force(tmp_context: Path) -> None:
    context_manager.create("y")
    with pytest.raises(PermissionError):
        context_manager.delete("y")
    context_manager.delete("y", force=True)
