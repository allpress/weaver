"""`weaver status` — daemon + recent audit."""
from __future__ import annotations

import click

from weaver import guardian as services


@click.command("status", help="Show warden daemon status and the tail of its audit log.")
@click.option("--audit-n", default=10, show_default=True, help="Audit lines to show")
def status(audit_n: int) -> None:
    h = services.health()
    click.echo(f"weaver import    : {'yes' if h.weaver_importable else 'no'}")
    click.echo(f"warden import    : {'yes' if h.warden_importable else 'no'}")
    click.echo(f"warden socket    : {services.warden_socket()}  exists={h.warden_socket_exists}")
    click.echo(f"warden pid alive : {h.warden_pid_alive}")
    click.echo(f"warden token     : {h.warden_token_present}")
    click.echo(f"warden policy    : {h.warden_policy_present}")

    if h.warden_importable:
        try:
            from warden.audit import Audit
            click.echo("")
            click.echo("recent audit:")
            for e in Audit().tail(audit_n):
                click.echo(f"  {e.get('result', '?'):9} {e.get('method', '?'):40} "
                           f"ctx={e.get('context') or '-'}")
        except Exception as e:  # noqa: BLE001
            click.echo(f"(could not read audit: {e})")
