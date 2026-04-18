"""Logger filter that redacts secret values. Applied on format, not after."""
from __future__ import annotations

import logging
import re
from threading import RLock

_LOCK = RLock()
_PATTERNS: list[tuple[re.Pattern[str], str]] = []


def register_redaction(value: str, *, label: str = "***") -> None:
    """Register a string that must never appear in logs verbatim."""
    if not value or len(value) < 6:
        return
    with _LOCK:
        _PATTERNS.append((re.compile(re.escape(value)), label))


def clear_redactions() -> None:
    with _LOCK:
        _PATTERNS.clear()


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:  # noqa: ARG002
        msg = record.getMessage()
        with _LOCK:
            for pat, label in _PATTERNS:
                msg = pat.sub(label, msg)
        record.msg = msg
        record.args = ()
        return True


def install() -> None:
    """Attach the redaction filter to the root logger. Idempotent."""
    root = logging.getLogger()
    for existing in root.filters:
        if isinstance(existing, RedactionFilter):
            return
    root.addFilter(RedactionFilter())
