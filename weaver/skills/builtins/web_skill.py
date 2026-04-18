"""Web skill. Thin surface over `wayfinder.browser.Session` for agent use.

Discoverable via `weaver skill list`. Wraps the common one-shot flows —
`observe_page` (fetch + observe), `extract_text_blocks`, `screenshot_page` —
so an agent driving weaver via the skill registry doesn't have to manage a
Session lifecycle.

For multi-step flows (click, fill, navigate) prefer driving
`wayfinder.browser.Session` directly — the guide is at
`wayfinder/wayfinder/browser/AGENTS.md`. This skill is the "one URL in, one
structured blob out" convenience layer.
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from weaver.skills.base import Skill, SkillManifest, SkillResult

log = logging.getLogger(__name__)


def _domains_for(url: str, extra: list[str] | None = None) -> list[str]:
    host = (urlparse(url).hostname or "").lower()
    root = host
    parts = host.split(".")
    if len(parts) >= 2:
        root = ".".join(parts[-2:])
    allowed = {root}
    for d in extra or []:
        allowed.add(d.lower().lstrip("."))
    allowed.discard("")
    return sorted(allowed)


class WebSkill(Skill):
    manifest = SkillManifest(
        name="web",
        kind="playwright",
        version="0.1.0",
        actions=[
            "observe_page",
            "extract_text_blocks",
            "screenshot_page",
        ],
        description=(
            "One-shot wayfinder.browser.Session flows: fetch+observe, "
            "extract readable text, screenshot. For multi-step flows, import "
            "wayfinder.browser.Session directly (see its AGENTS.md)."
        ),
        requires_secrets=[],
        risk="standard",
    )

    def execute(self, action: str, **kwargs: Any) -> SkillResult:
        if action == "observe_page":
            return self._observe_page(**kwargs)
        if action == "extract_text_blocks":
            return self._extract_text_blocks(**kwargs)
        if action == "screenshot_page":
            return self._screenshot_page(**kwargs)
        return SkillResult(ok=False, error=f"unknown action: {action}")

    # -- actions --

    def _observe_page(self, *, url: str,
                      identity: str = "default",
                      allowed_domains: list[str] | None = None,
                      headless: bool = True,
                      viewport_only: bool = True,
                      **_: Any) -> SkillResult:
        """Return the observation as a dict (handles, landmarks, text, fingerprint)."""
        try:
            from wayfinder.browser import LocalExecutor, Session
            from wayfinder.browser.models import to_dict
        except ImportError as e:
            return SkillResult(ok=False, error=f"wayfinder[browser] not installed: {e}")

        domains = _domains_for(url, allowed_domains)
        s = Session(LocalExecutor())
        try:
            opened = s.open(identity=identity, allowed_domains=domains, headless=headless)
            if not opened.ok:
                return SkillResult(ok=False, error=f"open: {opened.error_detail or opened.error}")
            nav = s.goto(url)
            if not nav.ok:
                return SkillResult(ok=False, error=f"goto: {nav.error_detail or nav.error}")
            obs = s.observe(viewport_only=viewport_only)
        finally:
            s.close()
        return SkillResult(ok=True, data=to_dict(obs))

    def _extract_text_blocks(self, *, url: str,
                             tags: list[str] | None = None,
                             identity: str = "default",
                             allowed_domains: list[str] | None = None,
                             headless: bool = True,
                             **_: Any) -> SkillResult:
        """Return just the readable text blocks (filtered by tag if provided)."""
        res = self._observe_page(url=url, identity=identity,
                                 allowed_domains=allowed_domains,
                                 headless=headless, viewport_only=False)
        if not res.ok:
            return res
        wanted = {t.lower() for t in (tags or [])}
        blocks = [
            {"tag": t["tag"], "text": t["text"], "landmark": t.get("landmark")}
            for t in res.data.get("text_blocks", [])
            if not wanted or t["tag"].lower() in wanted
        ]
        return SkillResult(ok=True, data={"url": res.data.get("url"),
                                           "title": res.data.get("title"),
                                           "blocks": blocks})

    def _screenshot_page(self, *, url: str, out_path: str,
                         identity: str = "default",
                         allowed_domains: list[str] | None = None,
                         full_page: bool = False,
                         **_: Any) -> SkillResult:
        import base64
        from pathlib import Path

        try:
            from wayfinder.browser import LocalExecutor, Session
        except ImportError as e:
            return SkillResult(ok=False, error=f"wayfinder[browser] not installed: {e}")

        domains = _domains_for(url, allowed_domains)
        s = Session(LocalExecutor())
        try:
            opened = s.open(identity=identity, allowed_domains=domains, headless=True)
            if not opened.ok:
                return SkillResult(ok=False, error=f"open: {opened.error_detail or opened.error}")
            nav = s.goto(url)
            if not nav.ok:
                return SkillResult(ok=False, error=f"goto: {nav.error_detail or nav.error}")
            shot = s.screenshot(full_page=full_page)
        finally:
            s.close()
        if not shot.ok:
            return SkillResult(ok=False, error=f"screenshot: {shot.error_detail or shot.error}")
        Path(out_path).write_bytes(base64.b64decode(shot.b64))
        return SkillResult(ok=True, data={"path": out_path,
                                           "width": shot.width, "height": shot.height})


SKILL = WebSkill()
