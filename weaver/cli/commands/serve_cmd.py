"""`weaver serve` — start warden in the foreground (passthrough)."""
from __future__ import annotations

import subprocess

import click


@click.command("serve", help="Run `warden serve` in the foreground.")
def serve() -> None:
    try:
        raise SystemExit(subprocess.call(["warden", "serve"]))
    except FileNotFoundError as e:
        raise click.ClickException(
            "`warden` CLI not found. Install: pip install -e path/to/warden"
        ) from e
