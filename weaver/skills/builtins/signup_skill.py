"""Signup skill. Playwright fills a signup form, Gmail skill reads the verification mail.

Only used when a site actually gates content. Requires:
  - `dangerously_use_playwright_token=True` on the caller,
  - per-context opt-in `allow_playwright_scrape = true` in context.ini,
  - TTY (non-interactive environments refuse).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

from weaver.auth import AuthResolver, SecretKind, SecretOrigin, SecretRef, get_default_store
from weaver.config import load_context, load_global
from weaver.paths import playwright_auth_dir
from weaver.skills.base import Skill, SkillManifest, SkillResult
from weaver.skills.builtins.gmail_skill import GmailSkill

log = logging.getLogger(__name__)


class SignupSkill(Skill):
    manifest = SkillManifest(
        name="signup",
        kind="playwright",
        version="0.1.0",
        actions=["signup_with_email_verification"],
        description=(
            "Playwright-driven signup using the aggregator mailbox for email verification. "
            "Last resort — only when the content is gated."
        ),
        requires_secrets=["gmail/app_password"],
        risk="dangerous",
    )

    def execute(self, action: str, **kwargs: Any) -> SkillResult:
        if action != "signup_with_email_verification":
            return SkillResult(ok=False, error=f"unknown action: {action}")

        context = kwargs.get("context")
        signup_url = kwargs.get("signup_url")
        if not context or not signup_url:
            return SkillResult(ok=False, error="need kwargs: context, signup_url")

        # --- enforce the triple-gated rule ---
        global_cfg = load_global()
        ctx_cfg = load_context(context)
        provider = kwargs.get("provider_name") or _host(signup_url)

        if not ctx_cfg.playwright_allowed.get(provider, False):
            return SkillResult(
                ok=False,
                error=(
                    f"context {context!r} has not opted into playwright scraping for "
                    f"{provider!r}. Add to contexts/{context}/context.ini:\n"
                    f"  [auth.providers.{provider}]\n"
                    f"  allow_playwright_scrape = true\n"
                    f"  playwright_scrape_reason = <why>"
                ),
            )
        if not kwargs.get("dangerously_use_playwright_token", False):
            return SkillResult(
                ok=False,
                error="pass dangerously_use_playwright_token=True to confirm",
            )

        # Ensure the resolver agrees (TTY check, CI check, env-var escape hatch).
        store = get_default_store(global_cfg)
        resolver = AuthResolver(store, global_cfg)
        if not resolver._playwright_permitted(ctx_cfg, provider):  # noqa: SLF001
            return SkillResult(ok=False, error="environment refuses playwright scrape")

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return SkillResult(
                ok=False,
                error="playwright not installed. pip install weaver[playwright] && playwright install chromium",
            )

        email_addr = kwargs.get("email") or _gmail_address(context)
        form = kwargs.get("form_fields") or {}
        email_field_selector = kwargs.get("email_field_selector", 'input[type="email"]')
        submit_selector = kwargs.get("submit_selector", 'button[type="submit"]')
        verify_link_selector = kwargs.get("verify_link_selector")   # optional post-verify click
        from_domain = kwargs.get("verification_from_domain", provider)
        timeout_s = int(kwargs.get("verification_timeout_s", 180))

        since = datetime.now(timezone.utc) - timedelta(seconds=30)
        cookies: list[dict[str, Any]] = []

        profile_dir = playwright_auth_dir(context, provider)
        profile_dir.mkdir(parents=True, exist_ok=True)

        with sync_playwright() as pw:
            browser_ctx = pw.chromium.launch_persistent_context(
                str(profile_dir), headless=False,
            )
            page = browser_ctx.new_page()
            page.goto(signup_url, wait_until="domcontentloaded")
            page.fill(email_field_selector, email_addr)
            for sel, value in form.items():
                try:
                    page.fill(sel, str(value))
                except Exception as e:  # noqa: BLE001
                    log.warning("form field %s fill failed: %s", sel, e)
            page.click(submit_selector)

            log.info("submitted signup; watching Gmail for verification from %s", from_domain)
            gmail = GmailSkill()
            vres = gmail.execute(
                "extract_verification_url",
                context=context,
                from_domain=from_domain,
                since=since.isoformat(),
                timeout_s=timeout_s,
            )
            if not vres.ok:
                browser_ctx.close()
                return SkillResult(ok=False, error=f"verification failed: {vres.error}")

            verify_url = vres.data.get("url")
            code = vres.data.get("code")
            if verify_url:
                page.goto(verify_url, wait_until="domcontentloaded")
            elif code:
                code_sel = kwargs.get("code_field_selector", 'input[name*="code"]')
                page.fill(code_sel, code)
                page.click(submit_selector)
            else:
                browser_ctx.close()
                return SkillResult(ok=False, error="verification email had no URL or code")

            if verify_link_selector:
                try:
                    page.click(verify_link_selector, timeout=5000)
                except Exception:  # noqa: BLE001
                    pass

            cookies = browser_ctx.cookies()
            browser_ctx.close()

        # Store the session as a playwright-scraped secret, TTL 8h.
        expires = datetime.utcnow() + timedelta(hours=8)
        ref = SecretRef(
            context=context, provider=provider, key="session",
            kind=SecretKind.scraped_session, origin=SecretOrigin.playwright_scrape,
            created_at=datetime.utcnow(), expires_at=expires,
        )
        serialized = _serialize_cookies(cookies)
        store.put(ref, serialized.encode("utf-8"))
        log.warning(
            "stored playwright_scrape session for %s (context=%s). "
            "Read-only by default; expires at %s UTC.",
            provider, context, expires.isoformat(),
        )

        return SkillResult(ok=True, data={
            "provider": provider,
            "context": context,
            "email_used": email_addr,
            "verify_url": verify_url,
            "code": code,
            "cookies_captured": len(cookies),
            "expires_at": expires.isoformat(),
        })


def _host(url: str) -> str:
    host = urlparse(url).hostname or ""
    return host.replace("www.", "").replace(".", "_")


def _gmail_address(context: str) -> str:
    """Fetch the stored Gmail username (email) without leaking the password."""
    global_cfg = load_global()
    ctx_cfg = load_context(context)
    store = get_default_store(global_cfg)
    resolver = AuthResolver(store, global_cfg)
    auth = resolver.resolve(ctx_cfg, "gmail")
    if auth.basic is None:
        raise RuntimeError("Gmail auth must be stored as basic_auth (email:app_password)")
    return auth.basic[0]


def _serialize_cookies(cookies: list[dict[str, Any]]) -> str:
    import json
    return json.dumps(cookies)


SKILL = SignupSkill()
