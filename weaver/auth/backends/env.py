"""Read-only environment-variable backend. Key shape: WEAVER_<CTX>_<PROVIDER>_<KEY>."""
from __future__ import annotations

import os
from datetime import datetime

from weaver.auth.resolver import SecretKind, SecretOrigin, SecretRef
from weaver.auth.store import SecretStore


class EnvStore(SecretStore):
    name = "env"

    def is_available(self) -> bool:
        return True  # env is always there

    def _env_key(self, ref: SecretRef) -> str:
        return f"WEAVER_{ref.context.upper()}_{ref.provider.upper()}_{ref.key.upper()}"

    def get(self, ref: SecretRef) -> bytes:
        v = os.environ.get(self._env_key(ref))
        if v is None:
            raise KeyError(f"env missing: {self._env_key(ref)}")
        return v.encode("utf-8")

    def put(self, ref: SecretRef, value: bytes) -> None:
        raise PermissionError("EnvStore is read-only. Export the variable externally.")

    def delete(self, ref: SecretRef) -> None:
        raise PermissionError("EnvStore is read-only.")

    def list(self, context: str, provider: str | None = None) -> list[SecretRef]:
        """Derived from the environment — only returns refs whose env var is set."""
        prefix = f"WEAVER_{context.upper()}_"
        if provider:
            prefix += f"{provider.upper()}_"
        out: list[SecretRef] = []
        for env_key in os.environ:
            if not env_key.startswith(prefix):
                continue
            rest = env_key[len(f"WEAVER_{context.upper()}_"):]
            parts = rest.split("_", 1)
            if len(parts) != 2:
                continue
            p_upper, k_upper = parts
            out.append(SecretRef(
                context=context,
                provider=p_upper.lower(),
                key=k_upper.lower(),
                kind=SecretKind.api_token,
                origin=SecretOrigin.env_var,
                created_at=datetime.utcnow(),
            ))
        return out
