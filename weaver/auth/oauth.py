"""OAuth2 refresh + interactive helper. Stubs — wire in per-provider as needed."""
from __future__ import annotations

from typing import TYPE_CHECKING

from weaver.auth.resolver import AuthResult

if TYPE_CHECKING:
    from weaver.auth.store import SecretStore


def refresh(store: "SecretStore", context: str, provider: str) -> AuthResult | None:
    """Exchange a stored refresh token for a fresh access token.

    No generic implementation — every OAuth server has its own token endpoint.
    Per-provider handlers register themselves here. Returns None if none apply.
    """
    handler = _REFRESH_HANDLERS.get(provider)
    if handler is None:
        return None
    return handler(store, context, provider)


def interactive_helper(store: "SecretStore", context: str, provider: str) -> AuthResult | None:
    """Launch the provider's interactive OAuth flow (device code or browser).

    Called only when TTY is available. Never invoked from a sandbox.
    """
    handler = _INTERACTIVE_HANDLERS.get(provider)
    if handler is None:
        return None
    return handler(store, context, provider)


_REFRESH_HANDLERS: dict[str, object] = {}
_INTERACTIVE_HANDLERS: dict[str, object] = {}


def register_refresh(provider: str, fn: object) -> None:
    _REFRESH_HANDLERS[provider] = fn


def register_interactive(provider: str, fn: object) -> None:
    _INTERACTIVE_HANDLERS[provider] = fn
