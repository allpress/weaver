"""Mail provider interface. Read-only by design for now."""
from __future__ import annotations

import re
from abc import abstractmethod
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from weaver.providers.base import Provider, ProviderCapability, Record


@dataclass(slots=True, frozen=True)
class MailMessage:
    uid: str
    from_addr: str
    from_name: str
    to_addrs: tuple[str, ...]
    subject: str
    date: datetime
    text_body: str
    html_body: str
    headers: dict[str, str] = field(default_factory=dict)

    def extract_urls(self, *, host_contains: str | None = None) -> list[str]:
        """Extract URLs from text + html. Dedups, keeps order."""
        urls: list[str] = []
        seen: set[str] = set()
        combined = f"{self.text_body}\n{self.html_body}"
        for m in _URL_RE.finditer(combined):
            url = m.group(0).rstrip(".,)'\">")
            if url in seen:
                continue
            if host_contains and host_contains not in url:
                continue
            seen.add(url)
            urls.append(url)
        return urls

    def extract_code(self, *, digits: int = 6) -> str | None:
        """Find a verification code: a run of N digits standing alone."""
        pat = re.compile(rf"(?<!\d)(\d{{{digits}}})(?!\d)")
        m = pat.search(self.text_body) or pat.search(self.html_body)
        return m.group(1) if m else None


_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)


class MailProvider(Provider):
    family = "mail"

    def capabilities(self) -> set[ProviderCapability]:
        return {ProviderCapability.read}

    @contextmanager
    @abstractmethod
    def session(self) -> Iterator["MailProvider"]:
        """Open and close the underlying connection. Use via `with`."""
        yield self  # pragma: no cover

    @abstractmethod
    def check(
        self,
        *,
        since: datetime | None = None,
        from_domain: str | None = None,
        subject_contains: str | None = None,
        limit: int = 25,
        mailbox: str = "INBOX",
    ) -> Iterable[MailMessage]: ...

    def wait_for(
        self,
        *,
        from_domain: str | None = None,
        subject_contains: str | None = None,
        since: datetime | None = None,
        timeout: timedelta = timedelta(minutes=3),
        poll_interval: timedelta = timedelta(seconds=10),
        mailbox: str = "INBOX",
    ) -> MailMessage | None:
        """Poll until a matching message arrives or we time out."""
        import time
        deadline = datetime.utcnow() + timeout
        baseline = since or (datetime.utcnow() - timedelta(seconds=5))
        while datetime.utcnow() < deadline:
            with self.session():
                for msg in self.check(
                    since=baseline,
                    from_domain=from_domain,
                    subject_contains=subject_contains,
                    limit=25,
                    mailbox=mailbox,
                ):
                    return msg
            time.sleep(poll_interval.total_seconds())
        return None

    def fetch(self, **query: Any) -> Iterable[Record]:
        """Provider interface: translate MailMessages into Records."""
        with self.session():
            for m in self.check(**query):
                yield Record(
                    id=m.uid,
                    type="mail_message",
                    source_uri=f"mail://{m.from_addr}/{m.uid}",
                    payload={
                        "subject": m.subject,
                        "from": m.from_addr,
                        "date": m.date.isoformat(),
                        "text": m.text_body[:4000],
                    },
                )
