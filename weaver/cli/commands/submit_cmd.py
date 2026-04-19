"""`weaver submit …` — fetch / review / apply for job boards.

Today: Anthropic (Greenhouse). First concrete use of the
``greenhouse_submitter`` wayfinder type.

Commands:

    weaver submit fetch    — pull open roles, generate plans
    weaver submit serve    — run the review dashboard
    weaver submit apply    — launch the submitter wayfinder for one or all approved
    weaver submit list     — print plan status as a table
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import click
import logging

# httpx is chatty at INFO; the progress bar we print is enough.
logging.getLogger("httpx").setLevel(logging.WARNING)

from weaver.paths import contexts_root
from weaver.submitter import (
    Applicant,
    GreenhouseClient,
    PlanBuilder,
    PlanStore,
    Voice,
    load_applicant,
)
from weaver.submitter.plan_builder import matches_curated_title, slugify


DEFAULT_CONTEXT = "anthropic"
DEFAULT_COMPANY = "Anthropic"


def _prefix_for(context: str) -> str:
    """Plan-file prefix for a context.

    Plans land at ``contexts/<context>/plans/<prefix>-<slug>.json``. We
    use the context name verbatim as the prefix so per-context dirs
    don't collide when multiple labs share the same job slug (e.g.
    "applied-ai-engineer" at both Anthropic and Scale AI).
    """
    return context


def _context_dir(context: str) -> Path:
    return contexts_root() / context


def _plans_dir(context: str) -> Path:
    return _context_dir(context) / "plans"


def _applicant_dir(context: str) -> Path:
    return _context_dir(context) / "applicant"


@click.group("submit", help="Fetch → review → apply job-application flow.")
def group() -> None:
    pass


# ---------- fetch ----------

@group.command("fetch")
@click.option("--context", "context", default=DEFAULT_CONTEXT, show_default=True)
@click.option("--company", default=DEFAULT_COMPANY, show_default=True)
@click.option("--limit", default=40, show_default=True)
@click.option("--all", "fetch_all", is_flag=True, help="Skip the curated title filter.")
@click.option("--throttle-ms", default=250, show_default=True)
def fetch(context: str, company: str, limit: int, fetch_all: bool, throttle_ms: int) -> None:
    """Pull the full open board and generate per-job plans.

    Plans land at ``contexts/<context>/plans/<prefix>-<slug>.json`` plus an
    ``<prefix>-index.json`` summary.
    """
    ctx_dir = _context_dir(context)
    plans_dir = _plans_dir(context)
    applicant = load_applicant(_applicant_dir(context))

    plans_dir.mkdir(parents=True, exist_ok=True)
    store = PlanStore(plans_dir)

    click.echo(f"Fetching {company} Greenhouse board…")
    with GreenhouseClient(company) as c:
        jobs = c.list_jobs()
        click.echo(f"  {len(jobs)} open roles")

        scope = jobs if fetch_all else [j for j in jobs if matches_curated_title(j.title)]

        # Dedupe by title (earliest first_published wins).
        seen: dict[str, Any] = {}  # type: ignore[name-defined]
        for j in scope:
            key = j.title.strip()
            prev = seen.get(key)
            if prev is None or (j.first_published or "") < (prev.first_published or ""):
                seen[key] = j
        unique = list(seen.values())
        work = unique[:limit]

        click.echo(
            f"  {len(scope)} matched curated filter → {len(unique)} unique titles "
            f"→ {len(work)} will be generated",
        )
        click.echo("")

        builder = PlanBuilder(applicant, company=company, voice=Voice())

        index_entries: list[dict[str, Any]] = []  # type: ignore[name-defined]
        for i, job in enumerate(work, 1):
            click.echo(f"[{i}/{len(work)}] {job.title} … ", nl=False)
            try:
                questions = c.get_questions(job.id)
            except Exception as e:   # noqa: BLE001
                click.echo(f"FAIL ({type(e).__name__}: {e})")
                continue
            plan = builder.build(job, questions)
            path = store.save(plan, prefix=_prefix_for(context))
            click.echo(
                f"ok  ({plan.answeredCount}/{plan.questionCount}, "
                f"{len(plan.unansweredLabels)} unhandled)"
            )
            index_entries.append({
                "slug": slugify(plan.title),
                "title": plan.title,
                "jobId": plan.jobId,
                "location": plan.location,
                "url": plan.url,
                "questionCount": plan.questionCount,
                "answeredCount": plan.answeredCount,
                "unansweredCount": len(plan.unansweredLabels),
                "approved": plan.approved,
                "submitted": plan.submitted,
                "generatedAt": plan.generatedAt,
            })
            time.sleep(throttle_ms / 1000.0)

    store.write_index({
        "generatedAt": _now_iso(),
        "totalOpen": len(jobs),
        "scoped": len(scope),
        "unique": len(unique),
        "generated": len(index_entries),
        "jobs": index_entries,
    }, prefix=_prefix_for(context))

    click.echo("")
    click.echo(f"Wrote {len(index_entries)} plans + index to {plans_dir}")
    click.echo(f"Review at: http://localhost:3456")


# ---------- list ----------

@group.command("list")
@click.option("--context", "context", default=DEFAULT_CONTEXT, show_default=True)
@click.option("--approved-only", is_flag=True)
@click.option("--json", "as_json", is_flag=True)
def list_cmd(context: str, approved_only: bool, as_json: bool) -> None:
    """Print every plan in the context with status."""
    store = PlanStore(_plans_dir(context))
    plans = store.list(prefix=_prefix_for(context))
    if approved_only:
        plans = [(s, p) for s, p in plans if p.approved and not p.submitted]

    if as_json:
        click.echo(json.dumps([
            {"slug": s, "title": p.title, "approved": p.approved,
             "submitted": p.submitted,
             "answered": f"{p.answeredCount}/{p.questionCount}"}
            for s, p in plans
        ], indent=2))
        return

    if not plans:
        click.echo("(no plans)")
        return
    click.echo(f"{'status':10s}  {'slug':55s}  {'answered':10s}  title")
    click.echo("-" * 100)
    for slug, p in plans:
        status = "submitted" if p.submitted else ("approved" if p.approved else "pending")
        click.echo(f"{status:10s}  {slug[:55]:55s}  {p.answeredCount:>3}/{p.questionCount:<3}    {p.title}")


# ---------- serve ----------

@group.command("serve")
@click.option("--context", "context", default=DEFAULT_CONTEXT, show_default=True)
@click.option("--port", default=3456, show_default=True)
def serve(context: str, port: int) -> None:
    """Run the review dashboard (stdlib http.server)."""
    from weaver.submitter.dashboard import serve as _serve

    ctx_dir = _context_dir(context)
    regenerate_cmd = [sys.executable, "-m", "weaver.cli.dispatcher",
                      "submit", "fetch", "--context", context]

    def apply_cmd_factory(**kw: Any) -> list[str]:   # type: ignore[name-defined]
        argv = [sys.executable, "-m", "weaver.cli.dispatcher",
                "submit", "apply", "--context", context]
        if kw.get("approved"):
            argv.append("--approved")
        if kw.get("slug"):
            argv.extend(["--slug", kw["slug"]])
        return argv

    _serve(
        context_root=ctx_dir,
        port=port,
        prefix=_prefix_for(context),
        regenerate_cmd=regenerate_cmd,
        apply_cmd_factory=apply_cmd_factory,
    )


# ---------- apply ----------

@group.command("apply")
@click.option("--context", "context", default=DEFAULT_CONTEXT, show_default=True)
@click.option("--slug", "slugs", multiple=True, help="Apply to these specific slugs. Repeatable.")
@click.option("--approved", is_flag=True, help="Apply to all approved-and-unsubmitted plans.")
@click.option("--headless", is_flag=True, help="Run headless (default: headful).")
@click.option("--send", is_flag=True, help="Press Submit. Default is fill + pause for review.")
def apply_cmd(context: str, slugs: tuple[str, ...], approved: bool,
              headless: bool, send: bool) -> None:
    """Launch the GreenhouseApplicantWayfinder for selected plans.

    Default is fill-and-pause: the browser opens, fills every mapped field,
    stops before Submit. Pass ``--send`` to actually submit.
    """
    from wayfinder.walkers import GreenhouseApplicantPlain

    applicant_dir = _applicant_dir(context)
    applicant = load_applicant(applicant_dir)
    store = PlanStore(_plans_dir(context))

    picks: list[tuple[str, "JobPlan"]] = []   # type: ignore[name-defined]
    prefix = _prefix_for(context)
    if slugs:
        for s in slugs:
            p = store.load(s, prefix=prefix)
            if p is None:
                raise click.ClickException(f"unknown slug: {s}")
            picks.append((s, p))
    elif approved:
        picks = [(s, p) for s, p in store.list(prefix=prefix)
                 if p.approved and not p.submitted]
    else:
        raise click.ClickException("pass --slug <slug> or --approved")

    if not picks:
        click.echo("Nothing to do.")
        return

    resume_pdf = applicant.resolve_path(applicant_dir, "resume_pdf")
    cover_pdf = applicant.resolve_path(applicant_dir, "cover_letter_pdf")
    resume_pdf_str = str(resume_pdf) if resume_pdf.exists() else ""
    cover_pdf_str = str(cover_pdf) if cover_pdf.exists() else None
    if not resume_pdf_str:
        click.echo(f"warn: resume PDF not found at {resume_pdf} — continuing without upload")

    w = GreenhouseApplicantPlain()

    from dataclasses import asdict as _asdict
    applicant_profile = applicant.to_dict()
    for slug, plan in picks:
        click.echo("")
        click.echo(f"=== {plan.title} ===")
        report = w.run(
            inputs={
                "plan": _asdict(plan),
                "resume_pdf_path": resume_pdf_str,
                "cover_letter_pdf_path": cover_pdf_str,
                "headless": headless,
                "pause_before_submit": not send,
                "applicant_profile": applicant_profile,
            },
            secret_resolver=None,
            emit=lambda e: click.echo(
                f"  [{e.kind}] {json.dumps(e.data)[:1200]}"
            ),
        )
        click.echo(f"  → status={report.status} ok={report.ok}")
        if report.output:
            safe = {k: v for k, v in report.output.items() if k != "screenshot_b64"}
            click.echo(f"  output: {json.dumps(safe)[:200]}")
            _persist_submission_evidence(store, slug, prefix,
                                          plan, report.output, send=send)


def _now_iso() -> str:
    import datetime as _dt
    return _dt.datetime.now(tz=_dt.timezone.utc).isoformat()


def _persist_submission_evidence(store: "PlanStore", slug: str, prefix: str,
                                  plan: "JobPlan", output: dict[str, Any],
                                  *, send: bool) -> None:   # type: ignore[name-defined]
    """Write the submission evidence back onto the plan JSON so the
    dashboard and later audits can see what happened.

    Records: submitted flag, timestamp, submission verification payload
    (``output['submission']``: url_changed, confirmation_found,
    matched_phrase, response_text preview, final_url, page_title).
    Only marks ``submitted`` True when the submitter reported confirmed.
    """
    try:
        path = store.path_for(slug, prefix=prefix)
        data = json.loads(path.read_text())
    except Exception as e:   # noqa: BLE001
        click.echo(f"  warn: could not load {slug} to persist evidence: {e}")
        return

    sub = output.get("submission") or {}
    confirmed = bool(sub.get("confirmed"))
    evidence = {
        "ranAt": _now_iso(),
        "sendMode": bool(send),
        "filled": int(output.get("filled") or 0),
        "flagged": list(output.get("flagged") or []),
        "unhandled": list(output.get("unhandled") or []),
        "clicked": bool(sub.get("clicked")),
        "confirmed": confirmed,
        "urlChanged": bool(sub.get("url_changed")),
        "confirmationFound": bool(sub.get("confirmation_found")),
        "matchedPhrase": sub.get("matched_phrase") or "",
        "finalUrl": sub.get("final_url") or output.get("final_url") or "",
        "pageTitle": sub.get("page_title") or "",
        "responseText": sub.get("response_text") or "",
    }
    # Preserve history — keep a list.
    history = list(data.get("submissionHistory") or [])
    history.append(evidence)
    data["submissionHistory"] = history[-10:]   # cap at 10 entries
    data["submission"] = evidence   # latest
    if confirmed and send:
        data["submitted"] = True
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


# click 8 doesn't love Any as a type hint in pep-604 style below in some envs
from typing import Any   # noqa: E402

__all__ = ["group"]
