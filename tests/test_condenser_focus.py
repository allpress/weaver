from __future__ import annotations

from weaver.contexts.manifest import FocusConfig
from weaver.indexer.condenser import _BASE_SYSTEM, build_system_prompt


def test_no_focus_returns_base() -> None:
    assert build_system_prompt(None) == _BASE_SYSTEM
    assert build_system_prompt(FocusConfig()) == _BASE_SYSTEM


def test_focus_topics_appear_in_prompt() -> None:
    f = FocusConfig(
        primary_topics=["quantum information", "error correction"],
        exclude_topics=["pop science"],
        entity_types=["paper", "institution"],
        extra_instruction="Be precise.",
    )
    p = build_system_prompt(f)
    assert "quantum information" in p
    assert "error correction" in p
    assert "pop science" in p
    assert "paper" in p
    assert "institution" in p
    assert "Be precise." in p
    # Base schema should still be present
    assert '"summary"' in p


def test_entity_type_note_only_when_types_given() -> None:
    f = FocusConfig(primary_topics=["x"])
    p = build_system_prompt(f)
    assert "Entity types of interest" not in p


def test_exclude_only_still_activates_focus_block() -> None:
    f = FocusConfig(exclude_topics=["marketing fluff"])
    p = build_system_prompt(f)
    assert "FOCUS" in p
    assert "marketing fluff" in p
