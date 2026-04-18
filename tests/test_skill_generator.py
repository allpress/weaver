from __future__ import annotations

from pathlib import Path

import pytest

# Skill generator walks source via the code parser (tree-sitter). Skip if
# the graph extra isn't installed in this environment.
pytest.importorskip("tree_sitter_languages")

from weaver.skills.generator import generate_from_codebase


def test_generator_infers_functions(tmp_path: Path) -> None:
    codebase = tmp_path / "src"
    codebase.mkdir()
    (codebase / "client.py").write_text(
        "def fetch_user(id): ...\n"
        "def _internal(): ...\n"
        "class Client:\n"
        "    def list_items(self): ...\n"
    )
    out = tmp_path / "skills_out"
    result = generate_from_codebase(
        name="demo", codebase=codebase, output_dir=out, kind="api",
    )
    assert "fetch_user" in result.inferred_actions
    assert "_internal" not in result.inferred_actions
    assert (result.directory / "_skill.py").exists()
    assert (result.directory / "README.md").exists()
