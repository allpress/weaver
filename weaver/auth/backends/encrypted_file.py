"""Fernet-encrypted-file fallback for headless environments."""
from __future__ import annotations

import getpass
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from weaver.auth.resolver import SecretKind, SecretOrigin, SecretRef
from weaver.auth.store import SecretStore, _delete_meta, _list_meta, _write_meta


class EncryptedFileStore(SecretStore):
    name = "encrypted_file"

    def __init__(self, path: Path) -> None:
        self._path = path
        self._fernet: Any | None = None

    def is_available(self) -> bool:
        try:
            import cryptography  # noqa: F401
        except ImportError:
            return False
        return True

    def _load_fernet(self) -> Any:
        if self._fernet is not None:
            return self._fernet
        import base64
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

        salt_path = self._path.with_suffix(".salt")
        if salt_path.exists():
            salt = salt_path.read_bytes()
        else:
            salt = _random_salt()
            salt_path.parent.mkdir(parents=True, exist_ok=True)
            salt_path.write_bytes(salt)

        passphrase = getpass.getpass("Master passphrase for encrypted secret file: ")
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(), length=32, salt=salt, iterations=390_000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))
        self._fernet = Fernet(key)
        return self._fernet

    def _load(self) -> dict[str, str]:
        if not self._path.exists():
            return {}
        f = self._load_fernet()
        blob = self._path.read_bytes()
        return json.loads(f.decrypt(blob).decode("utf-8"))

    def _save(self, data: dict[str, str]) -> None:
        f = self._load_fernet()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_bytes(f.encrypt(json.dumps(data).encode("utf-8")))

    def _addr(self, ref: SecretRef) -> str:
        return f"{ref.context}/{ref.provider}/{ref.kind.value}/{ref.key}"

    def get(self, ref: SecretRef) -> bytes:
        data = self._load()
        v = data.get(self._addr(ref))
        if v is None:
            raise KeyError(f"Secret not found: {ref.uri()}")
        return v.encode("utf-8")

    def put(self, ref: SecretRef, value: bytes) -> None:
        data = self._load()
        data[self._addr(ref)] = value.decode("utf-8")
        self._save(data)
        _write_meta(ref)

    def delete(self, ref: SecretRef) -> None:
        data = self._load()
        data.pop(self._addr(ref), None)
        self._save(data)
        _delete_meta(ref)

    def list(self, context: str, provider: str | None = None) -> list[SecretRef]:
        return _list_meta(context, provider)


def _random_salt() -> bytes:
    import secrets
    return secrets.token_bytes(16)
