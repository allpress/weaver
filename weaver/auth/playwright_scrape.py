"""Last-resort Playwright SSO scrape. Heavily gated; see auth-and-secrets.md."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from weaver.auth.resolver import AuthResult, SecretOrigin

if TYPE_CHECKING:
    from weaver.auth.store import SecretStore

log = logging.getLogger(__name__)

_DEFAULT_TTL = timedelta(hours=8)


def scrape(store: "SecretStore", context: str, provider: str) -> AuthResult | None:
    """Open a headed browser, let the user SSO, harvest cookies/bearer.

    Stubbed pending Wayfinder integration. The real implementation will:
      1. Launch chromium with a context-specific profile.
      2. Navigate to the provider's login page.
      3. Wait for post-login navigation (provider-specific predicate).
      4. Dump cookies + any Authorization header from intercepted requests.
      5. Store as SecretKind.scraped_session, origin=playwright_scrape, TTL=8h.
    """
    try:
        import playwright  # noqa: F401
    except ImportError:
        log.error(
            "playwright not installed. Install with: pip install weaver[playwright]"
        )
        return None

    log.warning(
        "playwright_scrape stub invoked for %s/%s — not yet implemented. "
        "Acquire the token out-of-band and store with: "
        "weaver secret set %s session --context %s --kind scraped_session",
        context, provider, provider, context,
    )
    return None


def _expiry() -> datetime:
    return datetime.utcnow() + _DEFAULT_TTL


def _origin() -> SecretOrigin:
    return SecretOrigin.playwright_scrape
