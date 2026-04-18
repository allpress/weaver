"""Review dashboard for generated application plans.

Stdlib-only HTTP server (no FastAPI, no Flask). Same shape as the
TypeScript dashboard it replaces — list page, detail page, context docs,
approve/unapprove, regenerate, apply (single + batch).

Serves from a single context directory::

    <context_root>/
        applicant/              — resume, cover letter, profile.yaml
        plans/                  — <prefix>-<slug>.json plans + <prefix>-index.json
        materials/              — thesis, wayfinder-idea, other context docs

Launch with:

    from weaver.submitter.dashboard import serve
    serve(context_root=Path("contexts/anthropic"), port=3456)
"""
from __future__ import annotations

import datetime as _dt
import html as _html
import json
import logging
import os
import re
import subprocess
import sys
import time
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from weaver.submitter.plan_builder import JobPlan, PlanStore

log = logging.getLogger(__name__)


# ---------- config ----------

DEFAULT_PREFIX = "anthropic"
DEFAULT_PORT = 3456


CONTEXT_DOCS: list[dict[str, str]] = [
    {"slug": "thesis", "file": "thesis.md", "title": "Thesis",
     "blurb": "One-page version of what I built and why, for Claude reviewers."},
    {"slug": "wayfinder-idea", "file": "wayfinder-idea.md", "title": "The agent-native browser",
     "blurb": "The distinctive idea, in spec form — handles, closed errors, diff, scope, cred-refusal."},
    {"slug": "resume", "file": "resume.md", "title": "Résumé",
     "blurb": "Career context. Refactored to explain what the trio does and why."},
]


CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #0f172a; color: #e2e8f0; padding: 24px; max-width: 1400px; margin: 0 auto; }
a { color: #60a5fa; text-decoration: none; }
a:hover { text-decoration: underline; }
header { margin-bottom: 24px; border-bottom: 1px solid #334155; padding-bottom: 16px; }
h1 { font-size: 1.6em; color: #f8fafc; margin-bottom: 4px; }
h1 small { color: #94a3b8; font-weight: 400; font-size: 0.65em; }
.breadcrumb { color: #94a3b8; font-size: 0.85em; margin-bottom: 8px; }
.bar { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; margin-bottom: 20px; }
.stat { background: #1e293b; padding: 10px 14px; border-radius: 8px; font-size: 0.85em; }
.stat strong { color: #f8fafc; font-size: 1.15em; }
.btn { background: #334155; color: #e2e8f0; border: 1px solid #475569; padding: 8px 14px;
       border-radius: 6px; font-size: 0.85em; cursor: pointer; font-family: inherit;
       text-decoration: none; display: inline-block; }
.btn:hover { background: #475569; text-decoration: none; }
.btn.primary { background: #2563eb; border-color: #3b82f6; }
.btn.primary:hover { background: #3b82f6; }
.btn.warn { background: #854d0e; border-color: #a16207; }
.btn.warn:hover { background: #a16207; }
.btn.success { background: #166534; border-color: #16a34a; }
.btn.success:hover { background: #16a34a; }
table { width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 8px; overflow: hidden; }
th { text-align: left; padding: 10px 14px; color: #94a3b8; border-bottom: 2px solid #334155;
     font-weight: 600; font-size: 0.8em; text-transform: uppercase; letter-spacing: 0.5px; }
td { padding: 10px 14px; border-bottom: 1px solid #334155; font-size: 0.9em; vertical-align: middle; }
tr:last-child td { border-bottom: none; }
tr:hover td { background: rgba(51, 65, 85, 0.3); }
.pill { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 0.75em;
        font-weight: 600; background: #334155; }
.pill.green { background: #166534; color: #bbf7d0; }
.pill.yellow { background: #854d0e; color: #fde68a; }
.pill.red { background: #7f1d1d; color: #fecaca; }
.pill.blue { background: #1e3a8a; color: #bfdbfe; }
.pill.gray { background: #334155; color: #cbd5e1; }
.question { background: #1e293b; border-radius: 8px; padding: 16px; margin-bottom: 12px;
            border-left: 3px solid #334155; }
.question.required { border-left-color: #f59e0b; }
.question.unhandled { border-left-color: #ef4444; }
.question .label { font-weight: 600; color: #f8fafc; margin-bottom: 4px; }
.question .meta { display: flex; gap: 8px; flex-wrap: wrap; font-size: 0.75em; color: #94a3b8; margin-bottom: 8px; }
.question .desc { font-size: 0.8em; color: #94a3b8; font-style: italic; margin-bottom: 8px; }
.question .answer { background: #0f172a; border-radius: 6px; padding: 12px; font-size: 0.9em;
                    line-height: 1.5; white-space: pre-wrap; color: #e2e8f0; }
.question .answer.empty { color: #64748b; font-style: italic; }
.question .options { font-size: 0.75em; color: #94a3b8; margin-top: 6px; }
.selected-opt { color: #4ade80; font-weight: 600; }
.note { background: #422006; border: 1px solid #a16207; padding: 6px 10px; border-radius: 4px;
        font-size: 0.75em; color: #fde68a; margin-top: 8px; }
.context-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
                 gap: 10px; margin-bottom: 20px; }
.context-card { background: #1e293b; padding: 14px 16px; border-radius: 8px;
                border-left: 3px solid #3b82f6; }
.context-card h3 { font-size: 0.95em; color: #f8fafc; margin-bottom: 4px; }
.context-card h3 a { color: inherit; }
.context-card p { color: #94a3b8; font-size: 0.82em; line-height: 1.4; }
.doc { background: #1e293b; border-radius: 8px; padding: 24px 32px; line-height: 1.6; }
.doc h1 { color: #f8fafc; font-size: 1.6em; margin-bottom: 12px; border-bottom: 1px solid #334155; padding-bottom: 8px; }
.doc h2 { color: #f8fafc; font-size: 1.2em; margin: 24px 0 8px; }
.doc h3 { color: #e2e8f0; font-size: 1em; margin: 18px 0 6px; }
.doc p { margin: 8px 0; color: #e2e8f0; }
.doc ul, .doc ol { margin: 8px 0 8px 24px; color: #e2e8f0; }
.doc li { margin: 4px 0; }
.doc code { background: #0f172a; color: #f0abfc; padding: 1px 5px; border-radius: 3px;
            font-size: 0.85em; font-family: ui-monospace, SFMono-Regular, monospace; }
.doc pre { background: #0f172a; padding: 12px 14px; border-radius: 6px; overflow-x: auto;
           margin: 10px 0; font-size: 0.82em; }
.doc pre code { background: none; padding: 0; color: #e2e8f0; }
.doc blockquote { border-left: 3px solid #475569; padding: 4px 14px; color: #94a3b8;
                  margin: 10px 0; font-style: italic; }
.doc hr { border: none; border-top: 1px solid #334155; margin: 20px 0; }
.doc a { color: #60a5fa; }
"""


# ---------- markdown renderer (no deps) ----------

def render_markdown(md: str) -> str:
    lines = md.splitlines()
    out: list[str] = []
    in_code = False
    in_list: str | None = None
    para: list[str] = []

    def flush_para() -> None:
        if para:
            out.append(f"<p>{_inline_fmt(' '.join(para))}</p>")
            para.clear()

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            out.append(f"</{in_list}>")
            in_list = None

    for raw in lines:
        line = raw.rstrip("\r")
        if line.startswith("```"):
            flush_para()
            close_list()
            if not in_code:
                out.append("<pre><code>")
                in_code = True
            else:
                out.append("</code></pre>")
                in_code = False
            continue
        if in_code:
            out.append(_html.escape(line))
            continue

        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            flush_para()
            close_list()
            depth = len(m.group(1))
            out.append(f"<h{depth}>{_inline_fmt(m.group(2))}</h{depth}>")
            continue

        m = re.match(r"^[-*]\s+(.*)$", line)
        if m:
            flush_para()
            if in_list != "ul":
                close_list()
                out.append("<ul>")
                in_list = "ul"
            out.append(f"<li>{_inline_fmt(m.group(1))}</li>")
            continue

        m = re.match(r"^\d+\.\s+(.*)$", line)
        if m:
            flush_para()
            if in_list != "ol":
                close_list()
                out.append("<ol>")
                in_list = "ol"
            out.append(f"<li>{_inline_fmt(m.group(1))}</li>")
            continue

        m = re.match(r"^>\s?(.*)$", line)
        if m:
            flush_para()
            close_list()
            out.append(f"<blockquote>{_inline_fmt(m.group(1))}</blockquote>")
            continue

        if line.startswith("---"):
            flush_para()
            close_list()
            out.append("<hr>")
            continue

        if not line.strip():
            flush_para()
            close_list()
            continue

        if in_list:
            close_list()
        para.append(line)

    flush_para()
    close_list()
    if in_code:
        out.append("</code></pre>")
    return "\n".join(out)


def _inline_fmt(s: str) -> str:
    t = _html.escape(s)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(^|[^*])\*([^*]+)\*", r"\1<em>\2</em>", t)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', t)
    return t


# ---------- page rendering ----------

def _page(title: str, body: str) -> bytes:
    html = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_html.escape(title)}</title>
<style>{CSS}</style>
</head>
<body>
{body}
</body></html>"""
    return html.encode("utf-8")


def _render_list(plans: list[tuple[str, JobPlan]],
                 totals: dict[str, Any]) -> bytes:
    approved = sum(1 for _, p in plans if p.approved)
    submitted = sum(1 for _, p in plans if p.submitted)
    pending = len(plans) - approved - submitted

    cards = "\n".join(
        f"""
        <div class="context-card">
          <h3><a href="/context/{d['slug']}">{_html.escape(d['title'])} →</a></h3>
          <p>{_html.escape(d['blurb'])}</p>
        </div>"""
        for d in CONTEXT_DOCS
    )

    if not plans:
        body = f"""
<header><div class="breadcrumb"><a href="/">dashboard</a></div><h1>Review queue</h1></header>
<div class="context-cards">{cards}</div>
<p style="margin-bottom:16px">No generated plans yet.</p>
<form method="POST" action="/regenerate">
  <button class="btn primary" type="submit">Generate plans from Greenhouse</button>
</form>"""
        return _page("Review queue", body)

    rows: list[str] = []
    for slug, p in plans:
        pct = round((p.answeredCount / p.questionCount) * 100) if p.questionCount else 0
        status = (
            '<span class="pill blue">submitted</span>' if p.submitted
            else '<span class="pill green">approved</span>' if p.approved
            else '<span class="pill yellow">pending review</span>'
        )
        unhandled = (
            f'<span class="pill red">{len(p.unansweredLabels)} unhandled</span>'
            if p.unansweredLabels else ''
        )
        rows.append(f"""
        <tr>
          <td><a href="/job/{slug}"><strong>{_html.escape(p.title)}</strong></a></td>
          <td>{_html.escape(p.location)}</td>
          <td>{p.answeredCount}/{p.questionCount} <span style="color:#64748b">({pct}%)</span> {unhandled}</td>
          <td>{status}</td>
          <td style="text-align:right">
            <a class="btn" href="{_html.escape(p.url)}" target="_blank" rel="noopener">Job →</a>
            <a class="btn primary" href="/job/{slug}">Review</a>
          </td>
        </tr>""")

    apply_all = ""
    if approved > 0:
        apply_all = f"""<form method="POST" action="/apply-approved">
    <button class="btn primary" type="submit"
            onclick="return confirm('Launch wayfinder apply for ALL {approved} approved-and-unsubmitted plans?');">
      Apply all approved ({approved}) →
    </button>
  </form>"""

    body = f"""
<header>
  <div class="breadcrumb"><a href="/">dashboard</a></div>
  <h1>Review queue <small>generated {_html.escape(totals.get('generatedAt', ''))}</small></h1>
</header>

<div class="context-cards">{cards}</div>

<div class="bar">
  <div class="stat"><strong>{len(plans)}</strong> plans</div>
  <div class="stat"><strong>{approved}</strong> approved</div>
  <div class="stat"><strong>{pending}</strong> pending</div>
  <div class="stat"><strong>{submitted}</strong> submitted</div>
  <div class="stat">{totals.get('totalOpen','-')} open on board · {totals.get('scoped','-')} matched filter · {totals.get('unique','-')} unique titles</div>
  <form method="POST" action="/regenerate" style="margin-left:auto">
    <button class="btn warn" type="submit" onclick="return confirm('Regenerate all plans from Greenhouse? ~30s.');">
      Regenerate all plans
    </button>
  </form>
  {apply_all}
</div>

<table>
  <thead>
    <tr><th>Role</th><th>Location</th><th>Answered</th><th>Status</th><th></th></tr>
  </thead>
  <tbody>{''.join(rows)}</tbody>
</table>

<p style="color:#64748b;font-size:0.8em;margin-top:24px">
  Answers are read-only on purpose — if the generator gets something wrong, fix the
  generator and regenerate. The point is an AI applying, not a human rewriting.
</p>"""
    return _page("Review queue", body)


def _render_detail(plan: JobPlan, slug: str) -> bytes:
    status = (
        '<span class="pill blue">submitted</span>' if plan.submitted
        else '<span class="pill green">approved</span>' if plan.approved
        else '<span class="pill yellow">pending review</span>'
    )

    qblocks: list[str] = []
    for q in plan.questions:
        req_cls = "required" if q.required else ""
        handled_cls = "unhandled" if q.strategy == "unhandled" else ""
        req_pill = '<span class="pill yellow">required</span>' if q.required else ''
        strategy_pill = f'<span class="pill gray">{_html.escape(q.strategy)}</span>'
        type_pill = f'<span class="pill gray">{_html.escape(q.fieldType or "?")}</span>'
        wc = len((q.proposedAnswer or "").split())
        wc_pill = f'<span class="pill gray">{wc} words</span>' if wc else ''
        desc = f'<div class="desc">{_html.escape(q.description)}</div>' if q.description else ''
        if q.proposedAnswer:
            ans = f'<div class="answer">{_html.escape(q.proposedAnswer)}</div>'
        else:
            ans = '<div class="answer empty">[no answer — will leave blank]</div>'
        opts = ""
        if q.options:
            parts: list[str] = []
            for o in q.options:
                picked = str(o.get("value")) == str(q.optionValue) if q.optionValue is not None else False
                cls = "selected-opt" if picked else ""
                check = " ✓" if picked else ""
                parts.append(f'<span class="{cls}">{_html.escape(str(o.get("label","")))}{check}</span>')
            opts = f'<div class="options"><span>options: {" · ".join(parts)}</span></div>'
        note = f'<div class="note">⚠ {_html.escape(q.note)}</div>' if q.note else ''

        qblocks.append(f"""
        <div class="question {req_cls} {handled_cls}">
          <div class="label">{_html.escape(q.label)}</div>
          <div class="meta">
            {req_pill} {strategy_pill} {type_pill} {wc_pill}
            <span style="color:#64748b">field={_html.escape(q.fieldName or "—")}</span>
          </div>
          {desc}
          {ans}
          {opts}
          {note}
        </div>""")

    if plan.approved:
        approve_action, approve_label, approve_class = "unapprove", "Unapprove", "btn warn"
    else:
        approve_action, approve_label, approve_class = "approve", "Approve for submission", "btn success"

    if plan.approved and not plan.submitted:
        apply_button = f"""<form method="POST" action="/job/{slug}/apply" style="display:inline">
         <button class="btn primary" type="submit"
                 onclick="return confirm('Launch wayfinder apply for: {_html.escape(plan.title).replace("'", "’")} ?');">
           Launch wayfinder apply →
         </button>
       </form>"""
    elif plan.submitted:
        apply_button = '<span class="pill blue">apply launched — check apply-logs/</span>'
    else:
        apply_button = ''

    body = f"""
<header>
  <div class="breadcrumb"><a href="/">dashboard</a> / job / {_html.escape(slug)}</div>
  <h1>{_html.escape(plan.title)} <small>{_html.escape(plan.location)}</small></h1>
</header>

<div class="bar">
  {status}
  <div class="stat"><strong>{plan.answeredCount}</strong>/{plan.questionCount} answered</div>
  <div class="stat">{len(plan.unansweredLabels)} unhandled</div>
  <div class="stat">generated {_html.escape(plan.generatedAt)}</div>
  <a class="btn" href="{_html.escape(plan.url)}" target="_blank" rel="noopener">Open on Greenhouse →</a>
  <form method="POST" action="/job/{slug}/{approve_action}" style="display:inline">
    <button class="{approve_class}" type="submit">{approve_label}</button>
  </form>
  {apply_button}
</div>

{''.join(qblocks)}

<p style="color:#64748b;font-size:0.8em;margin-top:24px">
  To change any of these, edit <code>weaver/submitter/plan_builder.py</code> or
  <code>weaver/submitter/voice.py</code> and regenerate. Inline editing is
  intentionally not offered.
</p>"""
    return _page(f"{plan.title} — review", body)


def _render_context_doc(slug: str, file_path: Path, md: str) -> bytes:
    others = "".join(
        f'<a class="btn" href="/context/{d["slug"]}">{_html.escape(d["title"])} →</a>'
        for d in CONTEXT_DOCS if d["slug"] != slug
    )
    doc_title = next((d["title"] for d in CONTEXT_DOCS if d["slug"] == slug), slug)
    body = f"""
<header>
  <div class="breadcrumb"><a href="/">dashboard</a> / context / {_html.escape(slug)}</div>
  <h1>{_html.escape(doc_title)} <small>{_html.escape(file_path.name)}</small></h1>
</header>
<div class="bar">
  {others}
  <span style="color:#64748b;margin-left:auto;font-size:0.8em">edit: <code>{_html.escape(str(file_path))}</code></span>
</div>
<div class="doc">{render_markdown(md)}</div>"""
    return _page(doc_title, body)


# ---------- HTTP server ----------

class _DashboardHandler(BaseHTTPRequestHandler):
    # Routes are installed on the class via ``build_handler`` below.
    store: PlanStore = None          # type: ignore[assignment]
    context_root: Path = None        # type: ignore[assignment]
    materials_dir: Path = None       # type: ignore[assignment]
    prefix: str = DEFAULT_PREFIX
    regenerate_cmd: list[str] = []   # argv for plan regeneration
    apply_cmd_factory: Callable[..., list[str]] = None  # type: ignore[assignment]
    apply_log_dir: Path = None       # type: ignore[assignment]

    # Silence the default stdout noise.
    def log_message(self, fmt: str, *args: Any) -> None:
        log.info("%s - %s", self.address_string(), fmt % args)

    # -- dispatch --

    def do_GET(self) -> None:   # noqa: N802
        try:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            if path == "/":
                self._list()
            elif path.startswith("/job/"):
                self._job_detail(path[len("/job/"):])
            elif path.startswith("/context/"):
                self._context_doc(path[len("/context/"):])
            else:
                self._not_found()
        except Exception as e:   # noqa: BLE001
            log.exception("GET %s failed", self.path)
            self._error(500, f"internal error: {type(e).__name__}: {e}")

    def do_POST(self) -> None:   # noqa: N802
        try:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            if path.startswith("/job/") and path.endswith("/approve"):
                self._toggle_approve(path.split("/")[2], approve=True)
            elif path.startswith("/job/") and path.endswith("/unapprove"):
                self._toggle_approve(path.split("/")[2], approve=False)
            elif path.startswith("/job/") and path.endswith("/apply"):
                self._apply_one(path.split("/")[2])
            elif path == "/regenerate":
                self._regenerate()
            elif path == "/apply-approved":
                self._apply_approved()
            else:
                self._not_found()
        except Exception as e:   # noqa: BLE001
            log.exception("POST %s failed", self.path)
            self._error(500, f"internal error: {type(e).__name__}: {e}")

    # -- GET handlers --

    def _list(self) -> None:
        plans = self.store.list(prefix=self.prefix)
        index = self.store.load_index(prefix=self.prefix) or {}
        totals = {
            "generatedAt": index.get("generatedAt") or _now_iso(),
            "totalOpen": index.get("totalOpen", "-"),
            "scoped": index.get("scoped", "-"),
            "unique": index.get("unique", "-"),
        }
        self._send_html(_render_list(plans, totals))

    def _job_detail(self, slug: str) -> None:
        plan = self.store.load(slug, prefix=self.prefix)
        if plan is None:
            self._error(404, f"no plan for slug {slug!r}")
            return
        self._send_html(_render_detail(plan, slug))

    def _context_doc(self, slug: str) -> None:
        doc = next((d for d in CONTEXT_DOCS if d["slug"] == slug), None)
        if doc is None:
            self._error(404, f"no context doc {slug!r}")
            return
        path = self.materials_dir / doc["file"]
        if not path.exists():
            self._error(404, f"file missing: {path}")
            return
        md = path.read_text(encoding="utf-8")
        self._send_html(_render_context_doc(slug, path, md))

    # -- POST handlers --

    def _toggle_approve(self, slug: str, *, approve: bool) -> None:
        plan = self.store.load(slug, prefix=self.prefix)
        if plan is None:
            self._error(404, "not found")
            return
        plan.approved = approve
        path = self.store.path_for(slug, prefix=self.prefix)
        path.write_text(json.dumps(asdict(plan), indent=2), encoding="utf-8")
        self._redirect(f"/job/{slug}")

    def _apply_one(self, slug: str) -> None:
        plan = self.store.load(slug, prefix=self.prefix)
        if plan is None:
            self._error(404, "not found")
            return
        if not plan.approved:
            self._error(400, "plan not approved yet")
            return
        self.apply_log_dir.mkdir(parents=True, exist_ok=True)
        log_path = self.apply_log_dir / f"{slug}-{int(time.time())}.log"
        with open(log_path, "ab") as f:
            subprocess.Popen(
                self.apply_cmd_factory(slug=slug),
                stdin=subprocess.DEVNULL, stdout=f, stderr=f,
                start_new_session=True,
            )
        plan.submitted = True
        path = self.store.path_for(slug, prefix=self.prefix)
        path.write_text(json.dumps(asdict(plan), indent=2), encoding="utf-8")
        self._redirect(f"/job/{slug}?applying=1")

    def _regenerate(self) -> None:
        if not self.regenerate_cmd:
            self._error(400, "no regenerate command configured")
            return
        self.apply_log_dir.mkdir(parents=True, exist_ok=True)
        log_path = self.apply_log_dir / f"regenerate-{int(time.time())}.log"
        with open(log_path, "ab") as f:
            subprocess.Popen(
                self.regenerate_cmd,
                stdin=subprocess.DEVNULL, stdout=f, stderr=f,
                start_new_session=True,
            )
        self._redirect("/?regenerating=1")

    def _apply_approved(self) -> None:
        self.apply_log_dir.mkdir(parents=True, exist_ok=True)
        log_path = self.apply_log_dir / f"batch-{int(time.time())}.log"
        with open(log_path, "ab") as f:
            subprocess.Popen(
                self.apply_cmd_factory(approved=True),
                stdin=subprocess.DEVNULL, stdout=f, stderr=f,
                start_new_session=True,
            )
        self._redirect("/?applying=batch")

    # -- helpers --

    def _send_html(self, body: bytes, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", location)
        self.end_headers()

    def _error(self, status: int, msg: str) -> None:
        body = f"<p>{_html.escape(msg)}</p><p><a href=\"/\">← back</a></p>".encode("utf-8")
        self._send_html(body, status=status)

    def _not_found(self) -> None:
        self._error(404, f"Not found: {self.path}")


# ---------- entry point ----------

def serve(
    *,
    context_root: Path,
    port: int = DEFAULT_PORT,
    prefix: str = DEFAULT_PREFIX,
    regenerate_cmd: list[str] | None = None,
    apply_cmd_factory: Callable[..., list[str]] | None = None,
) -> None:
    """Run the review dashboard against a context directory.

    Args:
        context_root: directory holding ``plans/``, ``applicant/``, ``materials/``.
        port: HTTP port (default 3456).
        prefix: plan filename prefix (default "anthropic").
        regenerate_cmd: argv for rebuilding plans; usually
            ``[sys.executable, "-m", "weaver", "submit", "fetch", "--context", ctx]``.
        apply_cmd_factory: callable returning argv to launch the submit
            wayfinder for either ``slug=<slug>`` or ``approved=True``.
    """
    plans_dir = context_root / "plans"
    materials_dir = context_root / "materials"
    apply_log_dir = context_root / "apply-logs"

    store = PlanStore(plans_dir)

    handler_class = type("_Handler", (_DashboardHandler,), {
        "store": store,
        "context_root": context_root,
        "materials_dir": materials_dir,
        "prefix": prefix,
        "regenerate_cmd": regenerate_cmd or [],
        "apply_cmd_factory": staticmethod(apply_cmd_factory or _default_apply_cmd),
        "apply_log_dir": apply_log_dir,
    })

    server = ThreadingHTTPServer(("127.0.0.1", port), handler_class)
    print(f"Dashboard running at http://localhost:{port}", flush=True)
    print(f"Context: {context_root}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down…", flush=True)
        server.server_close()


def _default_apply_cmd(*, slug: str | None = None, approved: bool = False) -> list[str]:
    argv = [sys.executable, "-m", "weaver", "submit", "apply"]
    if approved:
        argv.append("--approved")
    elif slug:
        argv.extend(["--slug", slug])
    return argv


def _now_iso() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).isoformat()


__all__ = ["CONTEXT_DOCS", "serve", "render_markdown"]
