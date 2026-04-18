"""`weaver secret` — set/show/list/rm. Values never come from args."""
from __future__ import annotations

import sys
from datetime import datetime

import click

from weaver.auth import SecretKind, SecretOrigin, SecretRef, get_default_store
from weaver.config import load_global


@click.group(help="Manage protected vars (tokens, credentials)")
def group() -> None:
    pass


_KINDS = [k.value for k in SecretKind]


@group.command("set")
@click.argument("provider")
@click.argument("key")
@click.option("--context", "context_name", required=True)
@click.option("--kind", type=click.Choice(_KINDS), default="api_token")
@click.option("--origin", type=click.Choice([o.value for o in SecretOrigin]),
              default="user_issued")
@click.option("--from-stdin", is_flag=True, help="Read value from stdin instead of prompting")
def set_cmd(provider: str, key: str, context_name: str,
            kind: str, origin: str, from_stdin: bool) -> None:
    if from_stdin:
        value = sys.stdin.read().rstrip("\n")
    else:
        value = click.prompt("value", hide_input=True, confirmation_prompt=True)
    if not value:
        raise click.UsageError("empty value")

    # Gmail app passwords copied from Google's yellow-box UI contain
    # non-breaking spaces between 4-char groups. Strip all Unicode whitespace
    # from the password half of a `user:pass` basic_auth value.
    if kind == SecretKind.basic_auth.value and ":" in value:
        import re
        user, _, pw = value.partition(":")
        pw_clean = re.sub(r"\s+", "", pw, flags=re.UNICODE)
        if pw_clean != pw:
            click.echo(f"note: stripped {len(pw) - len(pw_clean)} whitespace chars "
                       f"from password (NBSPs from the Google UI).")
        value = f"{user}:{pw_clean}"

    ref = SecretRef(
        context=context_name, provider=provider, key=key,
        kind=SecretKind(kind), origin=SecretOrigin(origin),
        created_at=datetime.utcnow(),
    )
    store = get_default_store(load_global())
    store.put(ref, value.encode("utf-8"))
    click.echo(f"stored {ref.uri()} [kind={kind} origin={origin}]")


@group.command("show")
@click.argument("provider")
@click.argument("key")
@click.option("--context", "context_name", required=True)
def show(provider: str, key: str, context_name: str) -> None:
    store = get_default_store(load_global())
    for ref in store.list(context_name, provider):
        if ref.key == key:
            click.echo(f"{ref.uri()}")
            click.echo(f"  kind:       {ref.kind.value}")
            click.echo(f"  origin:     {ref.origin.value}")
            click.echo(f"  created_at: {ref.created_at}")
            click.echo(f"  expires_at: {ref.expires_at}")
            return
    raise click.ClickException(f"not found: {provider}/{key} in {context_name}")


@group.command("list")
@click.option("--context", "context_name", required=True)
@click.option("--provider", default=None)
def list_secrets(context_name: str, provider: str | None) -> None:
    store = get_default_store(load_global())
    refs = store.list(context_name, provider)
    if not refs:
        click.echo("no secrets")
        return
    for r in refs:
        click.echo(f"{r.provider:16} {r.key:20} kind={r.kind.value:18} origin={r.origin.value}")


@group.command("rm")
@click.argument("provider")
@click.argument("key")
@click.option("--context", "context_name", required=True)
def rm(provider: str, key: str, context_name: str) -> None:
    store = get_default_store(load_global())
    for ref in store.list(context_name, provider):
        if ref.key == key:
            store.delete(ref)
            click.echo(f"deleted {ref.uri()}")
            return
    raise click.ClickException("not found")
