"""Auth resolver + types. Enforces the fixed precedence chain."""
from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from weaver.auth.store import SecretStore
    from weaver.config import ContextConfig, GlobalConfig

log = logging.getLogger(__name__)


class SecretKind(str, Enum):
    api_token = "api_token"
    oauth_refresh = "oauth_refresh"
    oauth_access = "oauth_access"
    basic_auth = "basic_auth"
    scraped_session = "scraped_session"
    ssh_key = "ssh_key"


class SecretOrigin(str, Enum):
    user_issued = "user_issued"
    oauth_official = "oauth_official"
    basic_credentials = "basic_credentials"
    playwright_scrape = "playwright_scrape"
    env_var = "env_var"


@dataclass(slots=True, frozen=True)
class SecretRef:
    context: str
    provider: str
    key: str
    kind: SecretKind
    origin: SecretOrigin
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None

    def uri(self) -> str:
        return f"secret://{self.context}/{self.provider}/{self.key}"


@dataclass(slots=True, frozen=True)
class AuthResult:
    provider: str
    context: str
    bearer: str | None = None
    basic: tuple[str, str] | None = None
    cookies: dict[str, str] | None = None
    origin: SecretOrigin = SecretOrigin.user_issued
    expires_at: datetime | None = None


class AuthenticationError(Exception):
    def __init__(self, *, context: str, provider: str, hint: str) -> None:
        super().__init__(f"auth failed: context={context} provider={provider}. {hint}")
        self.context = context
        self.provider = provider
        self.hint = hint


class UnsupportedAuthOriginForWrite(Exception):
    def __init__(self, *, provider: str, origin: SecretOrigin) -> None:
        super().__init__(f"provider {provider} refuses writes from origin {origin.value}")
        self.provider = provider
        self.origin = origin


class AuthResolver:
    """Single place where precedence is enforced. Providers call resolve()."""

    def __init__(self, store: "SecretStore", global_cfg: "GlobalConfig") -> None:
        self._store = store
        self._global = global_cfg

    def resolve(
        self,
        context_cfg: "ContextConfig",
        provider: str,
        *,
        dangerously_use_playwright_token: bool = False,
    ) -> AuthResult:
        context = context_cfg.name

        # 1. Env var override (CI / ephemeral).
        if (r := self._from_env(context, provider)) is not None:
            log.debug("auth step 1 (env) matched for %s/%s", context, provider)
            return r

        # 2. User-issued API token.
        if (r := self._load_bearer(context, provider, SecretKind.api_token,
                                    SecretOrigin.user_issued)) is not None:
            log.debug("auth step 2 (api_token) matched")
            return r

        # 3. Cached OAuth access token if still valid.
        if (r := self._load_oauth_access(context, provider)) is not None:
            log.debug("auth step 3 (oauth_access) matched")
            return r

        # 4. OAuth refresh -> access.
        if (r := self._refresh_oauth(context, provider)) is not None:
            log.debug("auth step 4 (oauth_refresh) matched")
            return r

        # 5. Basic auth.
        if (r := self._load_basic(context, provider)) is not None:
            log.debug("auth step 5 (basic) matched")
            return r

        # 6. Interactive OAuth helper (outside sandbox).
        if self._can_run_auth_helper():
            if (r := self._run_oauth_helper(context, provider)) is not None:
                log.debug("auth step 6 (oauth helper) matched")
                return r

        # 7. Last resort — Playwright scrape. Triple-gated.
        if dangerously_use_playwright_token:
            if self._playwright_permitted(context_cfg, provider):
                if (r := self._scrape_via_playwright(context, provider)) is not None:
                    log.warning(
                        "auth: using playwright_scrape origin for %s (context=%s). "
                        "Session-scoped; do not reuse for writes.",
                        provider, context,
                    )
                    return r

        raise AuthenticationError(
            context=context, provider=provider,
            hint=f"Run: weaver auth {provider} --context {context}",
        )

    # ---- step implementations ----

    def _from_env(self, context: str, provider: str) -> AuthResult | None:
        key = f"WEAVER_{context.upper()}_{provider.upper()}_TOKEN"
        v = os.environ.get(key)
        if v:
            return AuthResult(provider=provider, context=context, bearer=v,
                              origin=SecretOrigin.env_var)
        return None

    def _load_bearer(self, context: str, provider: str, kind: SecretKind,
                     origin: SecretOrigin) -> AuthResult | None:
        ref = self._store.find(context, provider, kind)
        if ref is None:
            return None
        value = self._store.get(ref)
        return AuthResult(provider=provider, context=context,
                          bearer=value.decode("utf-8"), origin=origin,
                          expires_at=ref.expires_at)

    def _load_oauth_access(self, context: str, provider: str) -> AuthResult | None:
        ref = self._store.find(context, provider, SecretKind.oauth_access)
        if ref is None:
            return None
        if ref.expires_at and ref.expires_at < datetime.utcnow():
            return None
        value = self._store.get(ref)
        return AuthResult(provider=provider, context=context,
                          bearer=value.decode("utf-8"),
                          origin=SecretOrigin.oauth_official,
                          expires_at=ref.expires_at)

    def _refresh_oauth(self, context: str, provider: str) -> AuthResult | None:
        # Hook for weaver/auth/oauth.py — stubbed; wire when a provider needs it.
        from weaver.auth.oauth import refresh  # lazy
        return refresh(self._store, context, provider)

    def _load_basic(self, context: str, provider: str) -> AuthResult | None:
        ref = self._store.find(context, provider, SecretKind.basic_auth)
        if ref is None:
            return None
        raw = self._store.get(ref).decode("utf-8")
        user, _, password = raw.partition(":")
        if not user:
            return None
        return AuthResult(provider=provider, context=context,
                          basic=(user, password),
                          origin=SecretOrigin.basic_credentials,
                          expires_at=ref.expires_at)

    def _can_run_auth_helper(self) -> bool:
        return sys.stdin.isatty() and sys.stdout.isatty()

    def _run_oauth_helper(self, context: str, provider: str) -> AuthResult | None:
        from weaver.auth.oauth import interactive_helper  # lazy
        return interactive_helper(self._store, context, provider)

    def _playwright_permitted(self, cfg: "ContextConfig", provider: str) -> bool:
        if not cfg.playwright_allowed.get(provider, False):
            log.info("playwright_scrape blocked: not enabled in context %s for %s",
                     cfg.name, provider)
            return False
        if not sys.stdin.isatty() and not self._global.auth_allow_playwright_in_ci:
            if os.environ.get("WEAVER_ALLOW_PLAYWRIGHT_IN_CI") != "1":
                log.info("playwright_scrape blocked: non-interactive and CI not allowed")
                return False
        return True

    def _scrape_via_playwright(self, context: str, provider: str) -> AuthResult | None:
        from weaver.auth.playwright_scrape import scrape  # lazy — optional dep
        return scrape(self._store, context, provider)
