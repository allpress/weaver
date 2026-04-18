"""SecretStore backend that forwards to a running Warden daemon.

In this mode, the sandbox cannot read secret values. `get()` raises by
default; use `get_value_ref()` to receive a `secret://` URI that Warden's
workers can dereference on your behalf.

Activate by setting in _config/defaults.ini:
    [secrets]
    backend = warden
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

from weaver.auth.resolver import SecretKind, SecretOrigin, SecretRef
from weaver.auth.store import SecretStore

log = logging.getLogger(__name__)


class SandboxCannotReadValue(PermissionError):
    pass


class WardenStore(SecretStore):
    """Talks to a running Warden over its Unix socket (or TCP loopback).

    Semantics are intentionally narrower than the keychain backends:
      - list() works — metadata only.
      - put() / delete() refuse; use `warden secret set` externally.
      - get() refuses with SandboxCannotReadValue by default. Set
        WEAVER_WARDEN_ALLOW_VALUE_READ=1 ONLY if the current process is itself
        the guardian (e.g. for bootstrap tests).
    """

    name = "warden"

    def __init__(self, *, tcp: tuple[str, int] | None = None) -> None:
        self._tcp = tcp
        self._allow_value_read = os.environ.get("WEAVER_WARDEN_ALLOW_VALUE_READ") == "1"

    def is_available(self) -> bool:
        try:
            from warden.client import WardenClient  # noqa: F401
        except ImportError:
            return False
        try:
            from warden import paths as lpaths
            sock = lpaths.socket_path()
        except Exception:  # noqa: BLE001
            return False
        if self._tcp is not None:
            return True
        return sock.exists()

    # --- metadata ops (allowed) ---

    def list(self, context: str, provider: str | None = None) -> list[SecretRef]:
        payload = self._call("secret.list", context=context, provider=provider)
        if not isinstance(payload, list):
            return []
        refs: list[SecretRef] = []
        for item in payload:
            try:
                refs.append(SecretRef(
                    context=item["uri"].split("//", 1)[1].split("/", 2)[0],
                    provider=item["provider"],
                    key=item["key"],
                    kind=SecretKind(item["kind"]),
                    origin=SecretOrigin(item["origin"]),
                    created_at=datetime.fromisoformat(item["created_at"]),
                    expires_at=(datetime.fromisoformat(item["expires_at"])
                                if item.get("expires_at") else None),
                ))
            except (KeyError, ValueError) as e:
                log.debug("skipping malformed secret row: %s", e)
        return refs

    # --- value ops (restricted) ---

    def get(self, ref: SecretRef) -> bytes:
        if not self._allow_value_read:
            raise SandboxCannotReadValue(
                f"Sandbox may not read secret values. "
                f"Use the value_ref `{ref.uri()}` via Warden workers instead."
            )
        # Emergency/bootstrap path only — there is intentionally no RPC method for
        # this. The flag just documents that the caller knows the risk.
        raise SandboxCannotReadValue(
            "value read not implemented over Warden RPC by design — use browser.fill "
            "with value_ref, or mail worker actions, instead of raw secret retrieval"
        )

    def get_value_ref(self, ref: SecretRef) -> str:
        """Return the `secret://` URI. Pass this to Warden workers as `value_ref`."""
        return ref.uri()

    def put(self, ref: SecretRef, value: bytes) -> None:
        raise PermissionError(
            "WardenStore is read-through. Store secrets via the guardian directly:\n"
            f"  weaver secret set {ref.provider} {ref.key} --context {ref.context} "
            f"--kind {ref.kind.value}\n"
            "(that runs against the configured keychain backend owned by Warden's host user)"
        )

    def delete(self, ref: SecretRef) -> None:
        raise PermissionError("WardenStore is read-through; delete on the guardian side")

    # --- rpc ---

    def _call(self, method: str, **params: Any) -> Any:
        from warden.client import WardenClient, WardenError
        with WardenClient.connect(tcp=self._tcp) as c:
            try:
                return c.call(method, **{k: v for k, v in params.items() if v is not None})
            except WardenError as e:
                log.warning("warden %s failed: %s", method, e)
                raise
