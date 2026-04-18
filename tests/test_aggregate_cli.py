"""End-to-end CLI test for `weaver aggregate` — dispatcher wiring and flow."""
from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from weaver.cli.dispatcher import cli


def test_aggregate_group_registered() -> None:
    runner = CliRunner()
    r = runner.invoke(cli, ["--help"])
    assert r.exit_code == 0
    assert "aggregate" in r.output


def test_aggregate_sources_list_from_seed() -> None:
    runner = CliRunner()
    r = runner.invoke(cli, ["aggregate", "sources", "list", "--json"])
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)
    names = {s["name"] for s in data}
    assert "martin-fowler" in names


def test_aggregate_cache_stats_empty(tmp_context: Path) -> None:
    runner = CliRunner()
    r = runner.invoke(cli, ["aggregate", "cache", "stats",
                            "--context", "ai-corpus", "--json"])
    assert r.exit_code == 0
    data = json.loads(r.output)
    assert data == {"total": 0, "per_source": {}}


def test_aggregate_fetch_unknown_source_errors(tmp_context: Path) -> None:
    runner = CliRunner()
    r = runner.invoke(cli, ["aggregate", "fetch",
                            "--context", "ai-corpus",
                            "--source", "does-not-exist"])
    assert r.exit_code != 0
    assert "unknown source" in r.output.lower()
