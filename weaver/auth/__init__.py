"""Auth & secrets. See extraction/04-providers/auth-and-secrets.md."""
from weaver.auth.resolver import (
    AuthenticationError,
    AuthResolver,
    AuthResult,
    SecretKind,
    SecretOrigin,
    SecretRef,
    UnsupportedAuthOriginForWrite,
)
from weaver.auth.store import SecretStore, get_default_store

__all__ = [
    "AuthResolver",
    "AuthResult",
    "AuthenticationError",
    "SecretKind",
    "SecretOrigin",
    "SecretRef",
    "SecretStore",
    "UnsupportedAuthOriginForWrite",
    "get_default_store",
]
