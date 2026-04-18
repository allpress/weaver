"""`weaver web …` — drive the AI-facing browser layer from the shell.

One-shot commands. CLI invocations don't share a live Session across calls —
for multi-step flows, import `wayfinder.browser.Session` from Python. See
`wayfinder/wayfinder/browser/AGENTS.md` for the full API.
"""
from __future__ import annotations

import json as jsonlib
import os
import sys
from dataclasses import asdict
from pathlib import Path

import click


def _open_session(identity: str, allowed_domains: list[str], *, headless: bool):
    from wayfinder.browser import LocalExecutor, Session
    s = Session(LocalExecutor())
    res = s.open(identity=identity, allowed_domains=allowed_domains, headless=headless)
    if not res.ok:
        raise click.ClickException(
            f"open failed: {res.error.value if res.error else 'unknown'} — {res.error_detail or ''}"
        )
    return s


def _domains_for(url: str, extra: tuple[str, ...]) -> list[str]:
    from urllib.parse import urlparse
    host = urlparse(url).hostname or ""
    root = host
    parts = host.split(".")
    if len(parts) >= 2:
        root = ".".join(parts[-2:])
    allowed = {root} | {d.lower().lstrip(".") for d in extra}
    allowed.discard("")
    return sorted(allowed)


@click.group("web", help="Drive the wayfinder browser Session from the CLI.")
def group() -> None:
    pass


@group.command("fetch")
@click.argument("url")
@click.option("--identity", default="default", show_default=True,
              help="Named identity — reuses cookies if you saved any.")
@click.option("--domain", "extra_domains", multiple=True,
              help="Extra allowed_domains entries. URL host root is always included.")
@click.option("--headed", is_flag=True, help="Show the browser window (default: headless).")
@click.option("--viewport-only/--full", default=True, show_default=True,
              help="Limit to viewport handles (faster) or the whole page.")
@click.option("--format", "fmt", type=click.Choice(["json", "summary"]), default="summary",
              show_default=True)
def fetch(url: str, identity: str, extra_domains: tuple[str, ...],
          headed: bool, viewport_only: bool, fmt: str) -> None:
    """Navigate to URL and dump the observation (handles, landmarks, text)."""
    from wayfinder.browser.models import to_dict
    allowed = _domains_for(url, extra_domains)
    s = _open_session(identity, allowed, headless=not headed)
    try:
        nav = s.goto(url)
        if not nav.ok:
            raise click.ClickException(
                f"goto failed: {nav.error.value if nav.error else 'unknown'} — {nav.error_detail or ''}"
            )
        obs = s.observe(viewport_only=viewport_only)
    finally:
        s.close()

    if fmt == "json":
        click.echo(jsonlib.dumps(to_dict(obs), indent=2))
        return
    click.echo(f"URL: {obs.url}")
    click.echo(f"Title: {obs.title}")
    click.echo(f"Handles: {len(obs.handles)} (truncated={obs.truncated})")
    click.echo(f"Landmarks: {len(obs.landmarks)}")
    click.echo(f"Text blocks: {len(obs.text_blocks)}")
    if obs.login_hint:
        click.echo(f"!! login wall: {obs.login_hint.provider} — {obs.login_hint.reason}")
    click.echo("")
    click.echo("-- handles (first 30) --")
    for h in obs.handles[:30]:
        marker = "*" if h.required else " "
        click.echo(f"  {marker} {h.handle}  {h.role:10s}  {h.name[:70]!r}")
    click.echo("")
    click.echo("-- text (first 10) --")
    for t in obs.text_blocks[:10]:
        snippet = t.text[:120].replace("\n", " ")
        click.echo(f"  [{t.tag}] {snippet}")


@group.command("text")
@click.argument("url")
@click.option("--identity", default="default", show_default=True)
@click.option("--domain", "extra_domains", multiple=True)
@click.option("--headed", is_flag=True)
@click.option("--tag", "tags", multiple=True,
              help="Filter text_blocks by tag (h1/h2/h3/p/li/…). Repeatable.")
def text(url: str, identity: str, extra_domains: tuple[str, ...],
         headed: bool, tags: tuple[str, ...]) -> None:
    """Dump just the readable text blocks from URL (h1/h2/p/…)."""
    allowed = _domains_for(url, extra_domains)
    s = _open_session(identity, allowed, headless=not headed)
    try:
        nav = s.goto(url)
        if not nav.ok:
            raise click.ClickException(f"goto failed: {nav.error_detail or nav.error}")
        obs = s.observe(viewport_only=False)
    finally:
        s.close()
    wanted = {t.lower() for t in tags}
    for t in obs.text_blocks:
        if wanted and t.tag.lower() not in wanted:
            continue
        click.echo(f"[{t.tag}] {t.text}")


@group.command("screenshot")
@click.argument("url")
@click.option("--identity", default="default", show_default=True)
@click.option("--domain", "extra_domains", multiple=True)
@click.option("--full-page", is_flag=True)
@click.option("--out", "out_path", required=True, type=click.Path(dir_okay=False, writable=True))
def screenshot(url: str, identity: str, extra_domains: tuple[str, ...],
               full_page: bool, out_path: str) -> None:
    """Navigate + screenshot + write PNG to --out."""
    import base64
    allowed = _domains_for(url, extra_domains)
    s = _open_session(identity, allowed, headless=True)
    try:
        nav = s.goto(url)
        if not nav.ok:
            raise click.ClickException(f"goto failed: {nav.error_detail or nav.error}")
        shot = s.screenshot(full_page=full_page)
    finally:
        s.close()
    if not shot.ok:
        raise click.ClickException(f"screenshot failed: {shot.error_detail or shot.error}")
    Path(out_path).write_bytes(base64.b64decode(shot.b64))
    click.echo(f"wrote {out_path} ({shot.width}x{shot.height})")


@group.command("identities")
def identities() -> None:
    """List identities held by the local IdentityStore (if one is configured).

    Identities persisted by warden live at ~/.warden/identities/ — view those
    via `warden call web.identity_list`.
    """
    root = Path(os.environ.get("WAYFINDER_IDENTITIES",
                               Path.home() / ".wayfinder" / "identities"))
    if not root.exists():
        click.echo(f"no local identity store at {root}")
        click.echo("(warden-managed identities: `warden call web.identity_list`)")
        return
    metas = sorted(root.glob("*.meta.json"))
    if not metas:
        click.echo(f"{root}: no identities saved")
        return
    for p in metas:
        try:
            data = jsonlib.loads(p.read_text())
        except jsonlib.JSONDecodeError:
            continue
        name = p.name[: -len(".meta.json")]
        click.echo(f"  {name}  provider={data.get('provider') or '-'}  "
                   f"domains={','.join(data.get('allowed_domains', []) or []) or '-'}")


@group.command("doctor")
def doctor() -> None:
    """Check wayfinder.browser prerequisites (playwright install, import path)."""
    problems: list[str] = []
    try:
        from wayfinder.browser import Session, LocalExecutor  # noqa: F401
        click.echo("  ok  wayfinder.browser importable")
    except ImportError as e:
        problems.append(f"wayfinder.browser not importable: {e}")
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        click.echo("  ok  playwright importable")
    except ImportError as e:
        problems.append(f"playwright missing — run: pip install 'wayfinder[browser]' ({e})")
    if problems:
        for p in problems:
            click.echo(f"  !!  {p}")
        sys.exit(1)
    click.echo("  hint: `playwright install chromium` if launches fail")


__all__ = ["group"]
