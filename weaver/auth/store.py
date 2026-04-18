"""SecretStore ABC + backend selection."""
from __future__ import annotations

import json
import platform
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from weaver.auth.resolver import SecretKind, SecretOrigin, SecretRef
from weaver.paths import config_dir

if TYPE_CHECKING:
    from weaver.config import GlobalConfig


class SecretStore(ABC):
    name: str = "unknown"

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def get(self, ref: SecretRef) -> bytes: ...

    @abstractmethod
    def put(self, ref: SecretRef, value: bytes) -> None: ...

    @abstractmethod
    def delete(self, ref: SecretRef) -> None: ...

    @abstractmethod
    def list(self, context: str, provider: str | None = None) -> list[SecretRef]: ...

    def find(self, context: str, provider: str, kind: SecretKind) -> SecretRef | None:
        for ref in self.list(context, provider):
            if ref.kind == kind:
                return ref
        return None


# ---------- Backend registry ----------

_META_DIR = config_dir() / "secret_meta"


def _meta_path(ref: SecretRef) -> Path:
    d = _META_DIR / ref.context / ref.provider
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{ref.key}.json"


def _write_meta(ref: SecretRef) -> None:
    data = {
        "context": ref.context,
        "provider": ref.provider,
        "key": ref.key,
        "kind": ref.kind.value,
        "origin": ref.origin.value,
        "created_at": ref.created_at.isoformat(),
        "expires_at": ref.expires_at.isoformat() if ref.expires_at else None,
    }
    _meta_path(ref).write_text(json.dumps(data, indent=2), encoding="utf-8")


def _read_meta(path: Path) -> SecretRef:
    data = json.loads(path.read_text(encoding="utf-8"))
    return SecretRef(
        context=data["context"],
        provider=data["provider"],
        key=data["key"],
        kind=SecretKind(data["kind"]),
        origin=SecretOrigin(data["origin"]),
        created_at=datetime.fromisoformat(data["created_at"]),
        expires_at=datetime.fromisoformat(data["expires_at"]) if data["expires_at"] else None,
    )


def _list_meta(context: str, provider: str | None) -> list[SecretRef]:
    base = _META_DIR / context
    if not base.exists():
        return []
    out: list[SecretRef] = []
    providers = [base / provider] if provider else [p for p in base.iterdir() if p.is_dir()]
    for pdir in providers:
        if not pdir.exists():
            continue
        for f in pdir.glob("*.json"):
            try:
                out.append(_read_meta(f))
            except Exception:
                continue
    return out


def _delete_meta(ref: SecretRef) -> None:
    p = _meta_path(ref)
    if p.exists():
        p.unlink()


def get_default_store(global_cfg: "GlobalConfig | None" = None) -> SecretStore:
    """Pick the backend based on config and platform availability.

    Precedence order when `backend = auto`:
      1. Warden (if a daemon is running) — sandbox can only read metadata.
      2. OS keychain — macOS Keychain / libsecret / Windows Credential Manager.
      3. Encrypted file — headless fallback.
      4. Env vars — read-only last resort.
    """
    import os as _os
    from weaver.auth.backends.encrypted_file import EncryptedFileStore
    from weaver.auth.backends.env import EnvStore
    from weaver.auth.backends.keychain import KeychainStore
    from weaver.auth.backends.warden_store import WardenStore

    requested = (global_cfg.secrets_backend if global_cfg else "auto").lower()
    prefer_warden = "WARDEN_SOCKET" in _os.environ or requested == "warden"

    candidates: list[SecretStore] = []
    if requested == "warden" or (requested == "auto" and prefer_warden):
        candidates.append(WardenStore())
    if requested in {"auto", "keychain", "libsecret", "windows"}:
        candidates.append(KeychainStore())
    if requested in {"auto", "encrypted_file"}:
        path = global_cfg.encrypted_file_path if global_cfg else config_dir() / ".secrets.enc"
        candidates.append(EncryptedFileStore(path))
    if requested in {"auto", "env"}:
        candidates.append(EnvStore())

    for c in candidates:
        if c.is_available():
            return c

    raise RuntimeError(
        f"No available secret backend (requested={requested}, platform={platform.system()})"
    )
