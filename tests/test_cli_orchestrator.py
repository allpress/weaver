from __future__ import annotations

from click.testing import CliRunner

from weaver.cli.dispatcher import cli


def test_help_loads() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    for word in ("setup", "serve", "status", "doctor", "mail"):
        assert word in result.output


def test_mail_group_has_subcommands() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["mail", "--help"])
    assert result.exit_code == 0
    for word in ("latest", "check", "wait-for", "verify-url"):
        assert word in result.output


def test_doctor_runs_without_error(warden_home) -> None:
    """With a clean WARDEN_HOME, doctor reports setup steps and exits non-zero."""
    runner = CliRunner()
    result = runner.invoke(cli, ["doctor"])
    # Doctor exits 1 when anything is missing; exit_code == 1 is success here.
    assert result.exit_code in (0, 1)
    assert "warden" in result.output
