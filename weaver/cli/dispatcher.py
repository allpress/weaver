"""Top-level CLI: `weaver <group> <subcommand>`.

Commands are registered via `click`. Every subcommand module exports a `group`
click.Group which `dispatcher.py` wires up — one plugin per command area.
"""
from __future__ import annotations

import logging
import sys

import click

from weaver.auth.redaction import install as install_redaction
from weaver.cli.commands.aggregate_cmd import group as aggregate_group
from weaver.cli.commands.auth_cmd import group as auth_group
from weaver.cli.commands.clone_cmd import group as clone_group
from weaver.cli.commands.context_cmd import group as context_group
from weaver.cli.commands.doctor_cmd import doctor as doctor_cmd
from weaver.cli.commands.graph_cmd import group as graph_group
from weaver.cli.commands.mail_cmd import group as mail_group
from weaver.cli.commands.rag_cmd import group as rag_group
from weaver.cli.commands.secret_cmd import group as secret_group
from weaver.cli.commands.serve_cmd import serve as serve_cmd
from weaver.cli.commands.setup_cmd import setup as setup_cmd
from weaver.cli.commands.skill_cmd import group as skill_group
from weaver.cli.commands.status_cmd import status as status_cmd
from weaver.cli.commands.submit_cmd import group as submit_group
from weaver.cli.commands.web_cmd import group as web_group


@click.group(help="Weaver — bidirectional context-weaving engine")
@click.option("--verbose", "-v", is_flag=True, help="Debug logging")
def cli(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    install_redaction()


cli.add_command(setup_cmd)
cli.add_command(serve_cmd)
cli.add_command(status_cmd)
cli.add_command(doctor_cmd)
cli.add_command(context_group, name="context")
cli.add_command(secret_group, name="secret")
cli.add_command(auth_group, name="auth")
cli.add_command(clone_group, name="clone")
cli.add_command(rag_group, name="rag")
cli.add_command(graph_group, name="graph")
cli.add_command(skill_group, name="skill")
cli.add_command(mail_group, name="mail")
cli.add_command(aggregate_group, name="aggregate")
cli.add_command(web_group, name="web")
cli.add_command(submit_group, name="submit")


def main() -> int:
    try:
        cli(standalone_mode=False)
        return 0
    except click.ClickException as e:
        e.show()
        return e.exit_code
    except click.Abort:
        click.echo("aborted", err=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
