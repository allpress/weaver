from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from weaver.cli.dispatcher import cli


def test_recipes_list_json_shape() -> None:
    result = CliRunner().invoke(cli, ["context", "recipes", "--json"])
    assert result.exit_code == 0, result.output
    rows = json.loads(result.output)
    slugs = {r["slug"] for r in rows}
    assert {"ai-corpus", "science-watch", "company-intel", "framework-watch"} <= slugs


def test_create_with_recipe_then_describe(tmp_context: Path) -> None:
    r = CliRunner().invoke(cli, [
        "context", "create", "my-ai", "--recipe", "ai-corpus",
    ])
    assert r.exit_code == 0, r.output
    assert "from recipe: ai-corpus" in r.output

    d = CliRunner().invoke(cli, ["context", "describe", "my-ai"])
    assert d.exit_code == 0, d.output
    assert "kind:" in d.output
    assert "ai-corpus" in d.output
    # Focus topics are printed
    assert "agentic programming" in d.output


def test_list_shows_kind_tag(tmp_context: Path) -> None:
    CliRunner().invoke(cli, ["context", "create", "a", "--recipe", "ai-corpus"])
    CliRunner().invoke(cli, ["context", "create", "b"])   # no recipe
    r = CliRunner().invoke(cli, ["context", "list", "--json"])
    assert r.exit_code == 0
    rows = {row["name"]: row for row in json.loads(r.output)}
    assert rows["a"]["kind"] == "knowledge-domain"
    assert rows["a"]["recipe"] == "ai-corpus"
    assert rows["b"]["kind"] == "custom"
    assert rows["b"]["recipe"] is None
    assert rows["a"]["has_manifest"] is True


def test_show_manifest_prints_path(tmp_context: Path) -> None:
    CliRunner().invoke(cli, ["context", "create", "c", "--recipe", "ai-corpus"])
    r = CliRunner().invoke(cli, ["context", "show-manifest", "c"])
    assert r.exit_code == 0
    assert r.output.strip().endswith("manifest.yaml")


def test_show_manifest_missing_errors(tmp_context: Path) -> None:
    # Context doesn't exist → manifest_path points at nothing.
    r = CliRunner().invoke(cli, ["context", "show-manifest", "nope"])
    assert r.exit_code != 0
    assert "no manifest" in r.output.lower()
