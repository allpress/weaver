"""`weaver setup` — first-run wizard. Wires warden + weaver + a starting context."""
from __future__ import annotations

import getpass
import subprocess
from dataclasses import dataclass

import click

from weaver import guardian as services


@dataclass(slots=True)
class SetupReport:
    warden_inited: bool
    warden_started: bool
    weaver_context: str | None
    gmail_stored: bool


@click.command("setup", help="First-run wizard: init warden, store Gmail app password, create context")
@click.option("--context", "context_name", default="ai-corpus", show_default=True,
              help="Weaver context to create (idempotent)")
@click.option("--email", "email_addr", default="doug.allpress.write@gmail.com", show_default=True,
              help="Gmail address for the aggregator inbox")
@click.option("--skip-gmail", is_flag=True, help="Don't prompt for the app password")
@click.option("--start-warden/--no-start-warden", default=True, show_default=True)
def setup(context_name: str, email_addr: str, skip_gmail: bool,
          start_warden: bool) -> None:
    report = run_setup(
        context_name=context_name,
        email_addr=email_addr,
        skip_gmail=skip_gmail,
        start_warden=start_warden,
        app_password_reader=_prompt_app_password,
    )
    click.echo("")
    click.echo("=== setup summary ===")
    click.echo(f"warden initialized: {report.warden_inited}")
    click.echo(f"warden running:     {report.warden_started}")
    click.echo(f"weaver context:     {report.weaver_context or '(skipped)'}")
    click.echo(f"gmail stored:       {report.gmail_stored}")


def run_setup(*, context_name: str, email_addr: str, skip_gmail: bool,
              start_warden: bool, app_password_reader=None) -> SetupReport:
    """Pure-ish logic so tests can drive it with injected readers."""
    warden_inited = services.warden_initialized()
    if not warden_inited:
        click.echo("→ initializing warden (cap.token + policy.yaml at ~/.warden/)")
        if services.warden_init_via_cli() != 0:
            raise click.ClickException("warden init failed")
        warden_inited = True

    started = services.warden_running()
    if start_warden and not started:
        click.echo("→ starting warden daemon in the background…")
        services.spawn_warden_detached()
        started = services.wait_for_warden(timeout_s=10.0)
        if not started:
            raise click.ClickException("warden failed to start within 10s")

    ctx_name: str | None = None
    try:
        subprocess.check_call([
            "weaver", "context", "create", context_name,
            "--display-name", context_name,
            "--activate",
        ])
        ctx_name = context_name
    except subprocess.CalledProcessError:
        click.echo(f"(context {context_name!r} already exists — leaving in place)")
        ctx_name = context_name
    except FileNotFoundError as e:
        raise click.ClickException(
            "`weaver` CLI not found. Install: pip install -e path/to/weaver"
        ) from e

    gmail_stored = False
    if not skip_gmail:
        reader = app_password_reader or _prompt_app_password
        app_pw = reader()
        if app_pw:
            # uttu/weaver stores basic_auth as "email:password". We go through
            # `weaver secret set --from-stdin` so the value never hits argv.
            value = f"{email_addr}:{app_pw}"
            proc = subprocess.Popen(
                [
                    "weaver", "secret", "set", "gmail", "app_password",
                    "--context", context_name,
                    "--kind", "basic_auth",
                    "--origin", "user_issued",
                    "--from-stdin",
                ],
                stdin=subprocess.PIPE,
            )
            proc.communicate(input=value.encode("utf-8"))
            if proc.returncode != 0:
                raise click.ClickException(
                    "weaver secret set failed; run it manually to see prompts."
                )
            gmail_stored = True

    return SetupReport(
        warden_inited=warden_inited,
        warden_started=started,
        weaver_context=ctx_name,
        gmail_stored=gmail_stored,
    )


def _prompt_app_password() -> str:
    click.echo("Enter the Gmail app password for doug.allpress.write@gmail.com.")
    click.echo("(From https://myaccount.google.com/apppasswords — 16 chars, any whitespace is stripped.)")
    try:
        raw = getpass.getpass("app password: ")
    except (EOFError, KeyboardInterrupt):
        click.echo("\n(skipped)")
        return ""
    # Google's yellow-box UI pastes NON-BREAKING SPACES (\xa0), not regular
    # spaces, between the 4-char groups. `str.strip()` / `.replace(" ", "")`
    # miss those. Strip every Unicode whitespace character instead.
    import re
    pw = re.sub(r"\s+", "", raw, flags=re.UNICODE)
    if pw and len(pw) != 16:
        click.echo(f"warning: expected 16 chars after stripping whitespace, got {len(pw)}. "
                   "Regenerate at https://myaccount.google.com/apppasswords if login fails.")
    return pw
