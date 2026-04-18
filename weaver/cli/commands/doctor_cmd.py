"""`weaver doctor` — report which pieces of the trio are wired up."""
from __future__ import annotations

import click

from weaver import guardian as services


@click.command("doctor", help="Check every piece of the trio and report missing links.")
def doctor() -> None:
    h = services.health()
    rows = [
        ("weaver importable", h.weaver_importable),
        ("warden importable", h.warden_importable),
        ("warden initialized (token)", h.warden_token_present),
        ("warden initialized (policy)", h.warden_policy_present),
        ("warden socket present", h.warden_socket_exists),
        ("warden pid alive", h.warden_pid_alive),
    ]
    bad = 0
    for label, ok in rows:
        mark = "✓" if ok else "✗"
        click.echo(f"  {mark} {label}")
        if not ok:
            bad += 1

    click.echo("")
    if bad == 0:
        click.echo("trio ready.")
        return

    click.echo("next steps:")
    if not h.weaver_importable:
        click.echo("  pip install -e path/to/weaver")
    if not h.warden_importable:
        click.echo("  pip install -e path/to/warden")
    if not (h.warden_token_present and h.warden_policy_present):
        click.echo("  weaver setup          # or: warden init")
    if h.warden_token_present and not h.warden_pid_alive:
        click.echo("  weaver serve          # or: warden serve")
    raise SystemExit(1)
