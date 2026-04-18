"""Gmail skill. Wraps GmailIMAPProvider behind the Skill contract."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from weaver.auth import AuthResolver, get_default_store
from weaver.config import load_context, load_global
from weaver.providers.mail.gmail_imap import GmailIMAPProvider, extract_verification_url
from weaver.skills.base import Skill, SkillManifest, SkillResult

log = logging.getLogger(__name__)


class GmailSkill(Skill):
    manifest = SkillManifest(
        name="gmail",
        kind="api",
        version="0.1.0",
        actions=[
            "check",
            "wait_for",
            "latest",
            "extract_verification_url",
        ],
        description="Read-only Gmail access via IMAP + app password.",
        requires_secrets=["gmail/app_password"],
        risk="standard",
    )

    def execute(self, action: str, **kwargs: Any) -> SkillResult:
        context = kwargs.pop("context", None)
        if not context:
            return SkillResult(ok=False, error="missing kwarg: context")

        try:
            provider = _build_provider(context)
        except Exception as e:  # noqa: BLE001
            return SkillResult(ok=False, error=f"auth/init failed: {e}")

        if action == "check":
            since = _parse_since(kwargs.get("since"))
            with provider.session():
                messages = list(provider.check(
                    since=since,
                    from_domain=kwargs.get("from_domain"),
                    subject_contains=kwargs.get("subject_contains"),
                    limit=int(kwargs.get("limit", 25)),
                    mailbox=kwargs.get("mailbox", "INBOX"),
                ))
            return SkillResult(ok=True, data=[_summarize(m) for m in messages])

        if action == "latest":
            with provider.session():
                messages = list(provider.check(limit=int(kwargs.get("limit", 5))))
            return SkillResult(ok=True, data=[_summarize(m) for m in messages])

        if action == "wait_for":
            timeout_s = int(kwargs.get("timeout_s", 180))
            poll_s = int(kwargs.get("poll_s", 10))
            msg = provider.wait_for(
                from_domain=kwargs.get("from_domain"),
                subject_contains=kwargs.get("subject_contains"),
                since=_parse_since(kwargs.get("since")),
                timeout=timedelta(seconds=timeout_s),
                poll_interval=timedelta(seconds=poll_s),
            )
            if msg is None:
                return SkillResult(ok=False, error="timeout")
            return SkillResult(ok=True, data=_summarize(msg, include_body=True))

        if action == "extract_verification_url":
            since = _parse_since(kwargs.get("since")) or (
                datetime.now(timezone.utc) - timedelta(minutes=10)
            )
            from_domain = kwargs.get("from_domain")
            timeout_s = int(kwargs.get("timeout_s", 180))
            msg = provider.wait_for(
                from_domain=from_domain,
                since=since,
                timeout=timedelta(seconds=timeout_s),
            )
            if msg is None:
                return SkillResult(ok=False, error="no verification email received")
            url = extract_verification_url(msg, host_contains=from_domain)
            code = msg.extract_code()
            return SkillResult(ok=True, data={
                "url": url,
                "code": code,
                "subject": msg.subject,
                "from": msg.from_addr,
                "uid": msg.uid,
            })

        return SkillResult(ok=False, error=f"unknown action: {action}")


def _build_provider(context_name: str) -> GmailIMAPProvider:
    global_cfg = load_global()
    context_cfg = load_context(context_name)
    store = get_default_store(global_cfg)
    resolver = AuthResolver(store, global_cfg)
    auth = resolver.resolve(context_cfg, "gmail")
    if auth.basic is None:
        raise RuntimeError(
            "Gmail secret must be stored as basic_auth. Run: "
            f"weaver secret set gmail app_password --context {context_name} --kind basic_auth"
        )
    email_addr, app_password = auth.basic
    return GmailIMAPProvider(email_addr=email_addr, app_password=app_password)


def _parse_since(raw: Any) -> datetime | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, datetime):
        return raw
    # Accept YYYY-MM-DD or ISO 8601.
    try:
        return datetime.fromisoformat(str(raw))
    except ValueError:
        try:
            return datetime.strptime(str(raw), "%Y-%m-%d")
        except ValueError as e:
            raise ValueError(f"bad since value: {raw!r}") from e


def _summarize(msg: Any, *, include_body: bool = False) -> dict[str, Any]:
    out = {
        "uid": msg.uid,
        "from": msg.from_addr,
        "from_name": msg.from_name,
        "to": list(msg.to_addrs),
        "subject": msg.subject,
        "date": msg.date.isoformat(),
    }
    if include_body:
        out["text"] = msg.text_body[:4000]
        out["urls"] = msg.extract_urls()
    return out


SKILL = GmailSkill()
