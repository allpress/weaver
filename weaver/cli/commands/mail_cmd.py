"""`weaver mail …` — read Gmail through the trio.

Path: weaver CLI → warden client → warden RPC → warden mail_worker →
weaver.providers.mail.gmail_imap → Gmail IMAP → scrubbed response back out.
"""
from __future__ import annotations

import json as jsonlib

import click

from weaver import guardian as services


@click.group("mail", help="Read the aggregator inbox through warden.")
def group() -> None:
    pass


@group.command("latest")
@click.option("--context", "context_name", default="ai-corpus", show_default=True)
@click.option("--limit", default=5, show_default=True)
@click.option("--json", "as_json", is_flag=True)
def latest(context_name: str, limit: int, as_json: bool) -> None:
    result = _call("mail.check", context=context_name, limit=limit)
    _emit(result, as_json=as_json)


@group.command("check")
@click.option("--context", "context_name", default="ai-corpus", show_default=True)
@click.option("--from", "from_domain", default=None)
@click.option("--subject", "subject_contains", default=None)
@click.option("--since", default=None, help="YYYY-MM-DD or ISO timestamp")
@click.option("--limit", default=25, show_default=True)
@click.option("--mailbox", default="INBOX", show_default=True)
@click.option("--json", "as_json", is_flag=True)
def check(context_name: str, from_domain: str | None, subject_contains: str | None,
          since: str | None, limit: int, mailbox: str, as_json: bool) -> None:
    params: dict[str, object] = {"context": context_name, "limit": limit, "mailbox": mailbox}
    if from_domain:
        params["from_domain"] = from_domain
    if subject_contains:
        params["subject_contains"] = subject_contains
    if since:
        params["since"] = since
    result = _call("mail.check", **params)
    _emit(result, as_json=as_json)


@group.command("wait-for")
@click.option("--context", "context_name", default="ai-corpus", show_default=True)
@click.option("--from", "from_domain", required=True)
@click.option("--subject", "subject_contains", default=None)
@click.option("--timeout", default=180, show_default=True)
@click.option("--json", "as_json", is_flag=True)
def wait_for(context_name: str, from_domain: str, subject_contains: str | None,
             timeout: int, as_json: bool) -> None:
    params: dict[str, object] = {
        "context": context_name, "from_domain": from_domain, "timeout_s": timeout,
    }
    if subject_contains:
        params["subject_contains"] = subject_contains
    result = _call("mail.wait_for", **params)
    _emit(result, as_json=as_json)


@group.command("classify")
@click.option("--context", "context_name", default="ai-corpus", show_default=True)
@click.option("--from", "from_domain", default=None,
              help="Filter messages by sender domain before classifying.")
@click.option("--since", default=None,
              help="Only messages since this date (YYYY-MM-DD or ISO).")
@click.option("--limit", default=50, show_default=True)
@click.option("--mailbox", default="INBOX", show_default=True)
@click.option("--category", "category_filter", default=None,
              help="Only show a specific category "
                   "(ack / rejection / interview / followup / auto / unknown).")
@click.option("--json", "as_json", is_flag=True)
def classify(context_name: str, from_domain: str | None, since: str | None,
             limit: int, mailbox: str, category_filter: str | None,
             as_json: bool) -> None:
    """Classify recent inbox messages by recruiter-email category.

    Rule-based (no LLM, no network beyond the IMAP fetch). Useful for
    tracking which applications have had responses, what kind, and
    which need a human look. See ``weaver.submitter.mail_classifier``.
    """
    from weaver.submitter.mail_classifier import classify as _classify

    params: dict[str, object] = {"context": context_name, "limit": limit,
                                  "mailbox": mailbox}
    if from_domain:
        params["from_domain"] = from_domain
    if since:
        params["since"] = since
    messages = _call("mail.check", **params)
    if not isinstance(messages, list):
        raise click.ClickException(
            f"unexpected mail.check return: {type(messages).__name__}"
        )

    rows: list[dict[str, object]] = []
    counts: dict[str, int] = {}
    for m in messages:
        if not isinstance(m, dict):
            continue
        c = _classify(m)
        if category_filter and c.category != category_filter:
            continue
        rows.append({
            "date": m.get("date"),
            "from": m.get("from"),
            "subject": m.get("subject"),
            "category": c.category,
            "confidence": c.confidence,
            "signal": c.signal,
        })
        counts[c.category] = counts.get(c.category, 0) + 1

    if as_json:
        click.echo(jsonlib.dumps({"summary": counts, "messages": rows},
                                  indent=2, default=str))
        return

    if not rows:
        click.echo("(no messages matched)")
        return

    # Category summary.
    total = sum(counts.values())
    order = ["interview", "followup", "rejection", "ack", "auto", "unknown"]
    pieces = [f"{k}={counts[k]}" for k in order if counts.get(k)]
    click.echo(f"{total} messages  ·  " + "  ".join(pieces))
    click.echo("-" * 100)
    for r in rows:
        cat = str(r["category"])
        conf = str(r["confidence"])
        marker = {"interview": "★", "followup": "!", "rejection": "✗",
                  "ack": "✓", "auto": ".", "unknown": "?"}.get(cat, " ")
        click.echo(f"{marker} {cat:10s}[{conf}]  "
                   f"{str(r['date'])[:19]:19s}  "
                   f"{str(r['from'])[:35]:35s}  "
                   f"{str(r['subject'])[:50]}")


@group.command("verify-url")
@click.option("--context", "context_name", default="ai-corpus", show_default=True)
@click.option("--from", "from_domain", required=True,
              help="Sender domain filter, e.g. 'github.com'")
@click.option("--timeout", default=180, show_default=True)
def verify_url(context_name: str, from_domain: str, timeout: int) -> None:
    result = _call("mail.extract_verification_url",
                   context=context_name, from_domain=from_domain, timeout_s=timeout)
    click.echo(jsonlib.dumps(result, indent=2, default=str))


# ---- helpers ----

def _call(method: str, **params: object) -> object:
    """Single seam for tests to monkeypatch."""
    try:
        with services.warden_client() as c:
            # WardenClient is typed as `object` at the service seam for test
            # monkeypatch friendliness; in production it's a real client.
            return c.call(method, **params)  # type: ignore[attr-defined]
    except RuntimeError as e:
        raise click.ClickException(str(e)) from e
    except Exception as e:  # noqa: BLE001
        # Surface warden errors compactly.
        raise click.ClickException(f"{type(e).__name__}: {e}")


def _emit(payload: object, *, as_json: bool) -> None:
    if as_json or not isinstance(payload, list):
        click.echo(jsonlib.dumps(payload, indent=2, default=str))
        return
    for m in payload:
        if not isinstance(m, dict):
            click.echo(str(m))
            continue
        click.echo(f"[{m.get('date', '?')}] {m.get('from', '?')}")
        click.echo(f"  {m.get('subject', '')}")
