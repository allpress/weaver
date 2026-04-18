"""`weaver auth` — walk the precedence chain, report which step matched."""
from __future__ import annotations

import click

from weaver.auth import AuthenticationError, AuthResolver, get_default_store
from weaver.config import load_context, load_global


@click.group(help="Authenticate providers (precedence: env → token → oauth → basic → helper → scrape)")
def group() -> None:
    pass


@group.command("check")
@click.argument("provider")
@click.option("--context", "context_name", required=True)
@click.option("--dangerously-use-playwright-token", is_flag=True,
              help="Last resort; requires per-context + per-provider opt-in")
def check(provider: str, context_name: str, dangerously_use_playwright_token: bool) -> None:
    global_cfg = load_global()
    context_cfg = load_context(context_name)
    store = get_default_store(global_cfg)
    resolver = AuthResolver(store, global_cfg)
    try:
        result = resolver.resolve(
            context_cfg, provider,
            dangerously_use_playwright_token=dangerously_use_playwright_token,
        )
    except AuthenticationError as e:
        raise click.ClickException(str(e)) from e

    click.echo(f"ok via origin={result.origin.value}")
    click.echo(f"  bearer present: {bool(result.bearer)}")
    click.echo(f"  basic present:  {bool(result.basic)}")
    click.echo(f"  cookies:        {len(result.cookies or {})}")
    click.echo(f"  expires_at:     {result.expires_at}")
