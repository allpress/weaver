"""OS keychain backend via `keyring`. Works on macOS, Linux (Secret Service), Windows."""
from __future__ import annotations

from weaver.auth.resolver import SecretKind, SecretRef
from weaver.auth.store import SecretStore, _delete_meta, _list_meta, _write_meta

_SERVICE_PREFIX = "weaver"


class KeychainStore(SecretStore):
    name = "keychain"

    def is_available(self) -> bool:
        try:
            import keyring
            keyring.get_keyring()
            return True
        except Exception:
            return False

    def _service(self, ref: SecretRef) -> str:
        return f"{_SERVICE_PREFIX}:{ref.context}:{ref.provider}"

    def _username(self, ref: SecretRef) -> str:
        return f"{ref.kind.value}:{ref.key}"

    def get(self, ref: SecretRef) -> bytes:
        import keyring
        v = keyring.get_password(self._service(ref), self._username(ref))
        if v is None:
            raise KeyError(f"Secret not found: {ref.uri()}")
        return v.encode("utf-8")

    def put(self, ref: SecretRef, value: bytes) -> None:
        import keyring
        keyring.set_password(self._service(ref), self._username(ref), value.decode("utf-8"))
        _write_meta(ref)

    def delete(self, ref: SecretRef) -> None:
        import keyring
        try:
            keyring.delete_password(self._service(ref), self._username(ref))
        except keyring.errors.PasswordDeleteError:
            pass
        _delete_meta(ref)

    def list(self, context: str, provider: str | None = None) -> list[SecretRef]:
        return _list_meta(context, provider)
