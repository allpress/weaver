"""Gmail via IMAP. Works with a Google App Password (requires 2FA on the account)."""
from __future__ import annotations

import email
import email.policy
import imaplib
import logging
import re
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any

from weaver.providers.base import ProviderCapability
from weaver.providers.mail.base import MailMessage, MailProvider

log = logging.getLogger(__name__)

_GMAIL_IMAP_HOST = "imap.gmail.com"
_GMAIL_IMAP_PORT = 993


class GmailIMAPProvider(MailProvider):
    """Read-only Gmail IMAP. Auth: email + app password (never the Google account password)."""

    name = "gmail"

    def __init__(self, *, email_addr: str, app_password: str,
                 host: str = _GMAIL_IMAP_HOST, port: int = _GMAIL_IMAP_PORT) -> None:
        self._email = email_addr
        self._pw = app_password
        self._host = host
        self._port = port
        self._conn: imaplib.IMAP4_SSL | None = None

    def capabilities(self) -> set[ProviderCapability]:
        return {ProviderCapability.read, ProviderCapability.basic_auth}

    @contextmanager
    def session(self) -> Iterator["GmailIMAPProvider"]:
        conn = imaplib.IMAP4_SSL(self._host, self._port)
        try:
            conn.login(self._email, self._pw)
        except imaplib.IMAP4.error as e:
            msg = str(e)
            if "Invalid credentials" in msg or "AUTHENTICATIONFAILED" in msg:
                raise RuntimeError(
                    "Gmail IMAP login failed. If this account has 2FA on, use an app password "
                    "from https://myaccount.google.com/apppasswords. Do NOT use your main "
                    "account password."
                ) from e
            raise
        self._conn = conn
        try:
            yield self
        finally:
            try:
                conn.logout()
            except Exception:  # noqa: BLE001
                pass
            self._conn = None

    def check(
        self,
        *,
        since: datetime | None = None,
        from_domain: str | None = None,
        subject_contains: str | None = None,
        limit: int = 25,
        mailbox: str = "INBOX",
    ) -> Iterable[MailMessage]:
        if self._conn is None:
            raise RuntimeError("no active IMAP session; wrap calls in `with provider.session():`")
        status, _ = self._conn.select(mailbox, readonly=True)
        if status != "OK":
            raise RuntimeError(f"IMAP SELECT {mailbox!r} failed: {status}")

        criteria = _build_search(since, from_domain, subject_contains)
        typ, data = self._conn.search(None, *criteria)
        if typ != "OK":
            raise RuntimeError(f"IMAP SEARCH failed: {typ}")
        ids = (data[0].split() if data and data[0] else [])
        # Newest first.
        for raw_id in reversed(ids[-limit:]):
            uid = raw_id.decode("ascii", errors="replace")
            typ, fetched = self._conn.fetch(raw_id, "(RFC822)")
            if typ != "OK" or not fetched or not isinstance(fetched[0], tuple):
                continue
            raw_bytes = fetched[0][1]
            if not isinstance(raw_bytes, (bytes, bytearray)):
                continue
            msg = email.message_from_bytes(bytes(raw_bytes), policy=email.policy.default)
            yield _to_mail_message(uid, msg)


def _build_search(since: datetime | None, from_domain: str | None,
                  subject_contains: str | None) -> tuple[str, ...]:
    parts: list[str] = []
    if since is not None:
        parts += ["SINCE", since.strftime("%d-%b-%Y")]
    if from_domain:
        parts += ["FROM", from_domain]
    if subject_contains:
        parts += ["SUBJECT", subject_contains]
    if not parts:
        parts = ["ALL"]
    return tuple(parts)


def _to_mail_message(uid: str, msg: EmailMessage) -> MailMessage:
    name, addr = parseaddr(str(msg.get("From", "")))
    to_header = str(msg.get("To", ""))
    to_addrs = tuple(parseaddr(p)[1] for p in _split_addrs(to_header) if parseaddr(p)[1])

    date_header = msg.get("Date")
    try:
        date = parsedate_to_datetime(str(date_header)) if date_header else datetime.now(timezone.utc)
    except (TypeError, ValueError):
        date = datetime.now(timezone.utc)
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)

    text_body, html_body = _extract_bodies(msg)
    headers = {k: str(v) for k, v in msg.items()}

    return MailMessage(
        uid=uid,
        from_addr=addr,
        from_name=name,
        to_addrs=to_addrs,
        subject=str(msg.get("Subject", "")),
        date=date,
        text_body=text_body,
        html_body=html_body,
        headers=headers,
    )


def _split_addrs(header_value: str) -> list[str]:
    # Respect commas inside quoted display names.
    parts: list[str] = []
    buf: list[str] = []
    in_quote = False
    for ch in header_value:
        if ch == '"':
            in_quote = not in_quote
        if ch == "," and not in_quote:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf).strip())
    return [p for p in parts if p]


def _extract_bodies(msg: EmailMessage) -> tuple[str, str]:
    text_body = ""
    html_body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain" and not text_body:
                text_body = _decode_part(part)
            elif ct == "text/html" and not html_body:
                html_body = _decode_part(part)
    else:
        ct = msg.get_content_type()
        payload = _decode_part(msg)
        if ct == "text/html":
            html_body = payload
        else:
            text_body = payload
    return text_body, html_body


def _decode_part(part: Any) -> str:
    try:
        payload = part.get_payload(decode=True)
        if payload is None:
            return ""
        charset = part.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")
    except Exception:  # noqa: BLE001
        return ""


# -------- convenience helpers for signup flows --------

_VERIFY_URL_HINT = re.compile(
    r"(verify|confirm|activate|validate|complete|continue)", re.IGNORECASE,
)


def extract_verification_url(msg: MailMessage, *, host_contains: str | None = None) -> str | None:
    """Pick the most likely verification URL from a message."""
    urls = msg.extract_urls(host_contains=host_contains)
    if not urls:
        return None
    # Score URLs by proximity to verify/confirm keywords; fall back to first.
    for url in urls:
        if _VERIFY_URL_HINT.search(url):
            return url
    return urls[0]
