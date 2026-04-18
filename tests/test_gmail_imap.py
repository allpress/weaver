from __future__ import annotations

import email
import email.policy
from datetime import datetime, timezone

from weaver.providers.mail.gmail_imap import (
    _build_search,
    _to_mail_message,
    extract_verification_url,
)


def _make_msg(body_text: str = "", body_html: str = "",
              subject: str = "Verify your email",
              from_addr: str = "no-reply@example.com") -> email.message.EmailMessage:
    msg = email.message.EmailMessage(policy=email.policy.default)
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = "doug.allpress.write@gmail.com"
    msg["Date"] = "Mon, 01 Jan 2024 12:00:00 +0000"
    if body_html:
        msg.set_content(body_text or "plain")
        msg.add_alternative(body_html, subtype="html")
    else:
        msg.set_content(body_text)
    return msg


def test_build_search_since_and_from() -> None:
    dt = datetime(2024, 3, 5, tzinfo=timezone.utc)
    crit = _build_search(dt, "github.com", "Verify")
    assert "SINCE" in crit
    assert "05-Mar-2024" in crit
    assert "FROM" in crit and "github.com" in crit
    assert "SUBJECT" in crit and "Verify" in crit


def test_build_search_defaults_to_all() -> None:
    crit = _build_search(None, None, None)
    assert crit == ("ALL",)


def test_extract_urls_and_code() -> None:
    msg = _to_mail_message("42", _make_msg(
        body_text="Click https://example.com/verify?token=abc123 or enter 482913 to verify.",
    ))
    assert "https://example.com/verify?token=abc123" in msg.extract_urls()
    assert msg.extract_code() == "482913"


def test_extract_verification_url_prefers_verify_keyword() -> None:
    msg = _to_mail_message("99", _make_msg(
        body_html='<a href="https://example.com/about">about</a>'
                  '<a href="https://example.com/confirm?t=xyz">confirm</a>',
    ))
    url = extract_verification_url(msg, host_contains="example.com")
    assert url == "https://example.com/confirm?t=xyz"


def test_host_filter() -> None:
    msg = _to_mail_message("1", _make_msg(
        body_text="bad https://phish.ru/evil and good https://github.com/verify/x",
    ))
    urls = msg.extract_urls(host_contains="github.com")
    assert urls == ["https://github.com/verify/x"]
