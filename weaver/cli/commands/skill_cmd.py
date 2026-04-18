"""`weaver skill` — list, run, scaffold from a codebase."""
from __future__ import annotations

from pathlib import Path

import click

from weaver.skills import get_registry
from weaver.skills.generator import generate_from_codebase


@click.group(help="Skill registry + codebase-derived scaffolding")
def group() -> None:
    pass


@group.command("list")
def list_skills() -> None:
    reg = get_registry()
    names = reg.list()
    if not names:
        click.echo("no skills registered")
        return
    for n in names:
        manifest = reg.get(n).manifest
        click.echo(f"{n:24} kind={manifest.kind:12} risk={manifest.risk:10} "
                   f"actions={len(manifest.actions)}")


@group.command("show")
@click.argument("name")
def show(name: str) -> None:
    skill = get_registry().get(name)
    m = skill.manifest
    click.echo(f"name:    {m.name}")
    click.echo(f"kind:    {m.kind}")
    click.echo(f"version: {m.version}")
    click.echo(f"risk:    {m.risk}")
    click.echo(f"desc:    {m.description}")
    click.echo(f"actions: {', '.join(m.actions) or '—'}")
    click.echo(f"needs:   {', '.join(m.requires_secrets) or '—'}")


@group.command("run")
@click.argument("name")
@click.argument("action")
@click.option("--kwarg", "kwargs_raw", multiple=True, help="key=value; repeatable")
def run(name: str, action: str, kwargs_raw: tuple[str, ...]) -> None:
    kwargs: dict[str, str] = {}
    for pair in kwargs_raw:
        if "=" not in pair:
            raise click.UsageError(f"--kwarg must be key=value, got {pair!r}")
        k, v = pair.split("=", 1)
        kwargs[k] = v
    result = get_registry().execute(name, action, **kwargs)
    if result.ok:
        click.echo(result.data)
    else:
        raise click.ClickException(result.error or "skill failed")


@group.command("new")
@click.argument("name")
@click.option("--from-codebase", "codebase", type=click.Path(path_type=Path, exists=True),
              required=True, help="Path to an existing codebase to scaffold from")
@click.option("--output-dir", type=click.Path(path_type=Path), default=Path("skills_user"))
@click.option("--kind", default="api", help="api | playwright | parser | domain")
def new(name: str, codebase: Path, output_dir: Path, kind: str) -> None:
    """Scaffold a new skill by scanning an existing codebase."""
    result = generate_from_codebase(
        name=name, codebase=codebase, output_dir=output_dir, kind=kind,
    )
    click.echo(f"scaffolded skill '{result.name}' at {result.directory}")
    if result.inferred_actions:
        click.echo(f"  inferred {len(result.inferred_actions)} action(s)")
    for note in result.notes:
        click.echo(f"  note: {note}")
    click.echo("Next: edit _skill.py to wire the real adapter, then: weaver skill list")
