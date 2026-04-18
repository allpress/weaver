from __future__ import annotations

from click.testing import CliRunner

from weaver.cli.dispatcher import cli


def test_cli_help_loads() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    for word in ("setup", "serve", "status", "doctor",
                 "context", "clone", "rag", "graph", "skill", "mail"):
        assert word in result.output, f"missing '{word}' in help output"


def test_context_list_empty(tmp_context, monkeypatch) -> None:
    # tmp_context monkeypatches paths.repo_root.
    runner = CliRunner()
    result = runner.invoke(cli, ["context", "list"])
    assert result.exit_code == 0
